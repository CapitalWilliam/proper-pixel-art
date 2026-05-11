# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

`proper-pixel-art` 是一个 Python 工具,用于将 **生成式模型(如 GPT-4o)产出或低质量网络上传的"伪像素风"图像** 还原为 **真正分辨率的像素画**。核心难点是这类输入图像往往高分辨率、有噪声、网格不对齐,无法用普通下采样处理。

包管理使用 [`uv`](https://docs.astral.sh/uv/),构建后端为 hatchling。Python 要求 `>=3.12`(CI 矩阵覆盖 3.12/3.13/3.14)。

## 常用命令

所有命令通过 `uv` 运行,无需手动激活虚拟环境。

```bash
# 安装依赖(默认环境 + dev 组)
uv sync

# 安装可选 extras
uv sync --extra web        # gradio,启用 ppa-web 网页 UI
uv sync --extra scripts    # openai + python-dotenv,启用 ppa-gen

# 运行测试(包含 -s 可看到产出路径)
uv run pytest
uv run pytest -s
uv run pytest tests/test_colors.py::TestGetCellColorWithAlpha   # 单个用例

# Lint / 格式化(CI 会跑这两条)
uv run ruff check
uv run ruff format --check     # CI 用,本地修复时改成 `uv run ruff format`

# 三个 console 入口
uv run ppa <input> -o <output> -c 16 -s 20 -t                # CLI 像素化(默认裁剪为正方形)
uv run ppa <input> -o <output> -c 16 -s 20 -t --no-square    # 关闭"裁剪到正方形"
uv run ppa-web                                                # Gradio 网页(http://127.0.0.1:7860)
uv run ppa-gen --prompt "16 bit pixel art ..."                # 调 OpenAI 生成后再像素化(需 .env)
```

部署相关:仓库根有 `app.py`,是 **Hugging Face Spaces 入口**(`from proper_pixel_art.web import create_demo`)。`.github/workflows/publish.yml` 在 GitHub Release 时自动发布到 PyPI。

## 算法架构(核心)

整条算法链都收束在 `proper_pixel_art/pixelate.py` 的 `pixelate()` 中,理解它就能改动大多数行为。

### 数据流

```
PIL.Image (RGBA)
   │
   ├─► mesh.compute_mesh_with_scaling()        # 网格检测(自动 fallback)
   │      │
   │      ├─ utils.crop_border()               # 边缘 2 像素裁剪
   │      ├─ colors.clamp_alpha(mode="L")      # 把 alpha<128 的像素填成"远离主色"的背景色
   │      ├─ cv2.Canny → mesh.close_edges      # 边缘 + 形态学闭运算
   │      ├─ mesh.detect_grid_lines            # 概率霍夫变换,仅保留近似 H/V 直线 + 聚类
   │      ├─ mesh.get_pixel_width              # 取直线间距中位数(过滤上下 20% 百分位)
   │      └─ mesh.homogenize_lines             # 用估算的 pixel_width 补齐缺失网格线
   │
   ├─► 颜色处理两条路径(由 num_colors 是否为 None 决定):
   │      ▸ 量化路径:colors.palette_img() 用 PIL Quantize.MAXCOVERAGE → RGB
   │      ▸ 跳过量化:直接走 RGBA,后续 cell 颜色用 offset-binning 算法
   │
   ├─► utils.scale_img()                       # 把图像缩到与 mesh 一致的尺度
   │
   ├─► pixelate.downsample()                   # 逐 cell 取代表色 → 输出 RGBA
   │      ▸ 量化:colors.get_cell_color_with_alpha() — 多数投票 RGB + 原图 alpha
   │      ▸ 不量化:colors.get_cell_color_skip_quantization() — offset-binning 找主导色
   │
   ├─► (可选) colors.make_background_transparent()   # 把和边缘主色相同的所有像素 alpha=0
   ├─► (可选,默认开) utils.trim_alpha_to_square()    # 按 alpha>=128 取 bbox 裁剪 + 短边补透明像素到正方形
   └─► (可选) utils.scale_img(scale_result)          # 最近邻放大输出
```

**顺序敏感**:`trim_alpha_to_square` **必须**在 `make_background_transparent` 之后(包含它产生的透明像素),且在 `scale_result` 之前(bbox 在真实像素分辨率上量,避免最近邻放大产生的 off-by-N)。

### 关键设计点(改代码前务必理解)

- **网格检测的 fallback 机制**:`compute_mesh_with_scaling()` 先在 `initial_upscale_factor`(默认 2)放大后的图上跑检测,如果只检测到 trivial 网格(只剩图像四角),自动回退到原图。修改默认 upscale 时要保留这个 fallback。

- **透明度的"50% 多数表决"**:所有 cell 颜色函数(`get_cell_color_with_alpha`、`get_cell_color_skip_quantization`)统一使用 `ALPHA_THRESHOLD = 128`,且一个 cell 中只要 **不透明像素 ≤ 50%** 就整体输出 `(0,0,0,0)`。`_is_majority_transparent` 是这个规则的唯一入口,改阈值或边界判定都从那里改。

- **Offset-binning 主导色算法**(`colors._dominant_rgb_by_binning`):跳过量化时使用。把 RGB 空间分两套偏移 1/2 bin 的 5×5×5 网格(bin_size=52),取主导 bin 较大者的中位数颜色。这是为了解决"主色刚好跨在 bin 边界两侧、被拆成两个小 bin"的问题。`<=3 像素` 走特殊路径(直接中位数),修改前请看 `test_bin_boundary_handled` 等单测。

- **量化器选择**:`palette_img()` 默认用 `Quantize.MAXCOVERAGE`(经验上整体最优)。README 提到某些图需要把 `num_colors` 提高很多或换 `Quantize.FASTOCTREE` 才正常 — 用户调参时可能会要求换算法。

- **`pixel_width` 手动覆盖**:用户可以跳过自动估算的网格步长(`get_pixel_width`),CLI 是 `-w`,Python API 是 `pixel_width=`。修改 mesh 算法时要确保这条手动路径仍然生效。

- **CLI 参数复用**:`scripts/ppa_gen.py` 通过 `proper_pixel_art.cli.add_pixelation_args()` 共享了 `-c/-s/-t/-w/-u/--no-square` 等参数。给 CLI 加新参数时,应该加进 `add_pixelation_args` 而不是 `parse_args`,否则 `ppa-gen` 拿不到。

- **`crop_to_square` 默认开启**:`pixelate(crop_to_square=True)` 是默认行为,CLI 用 `--no-square` 关闭(`dest="crop_to_square"`、`action="store_false"`),Web UI 是默认勾选的 `Crop to Square` 复选框。三个入口的默认语义必须保持一致 — 改默认时三处都要改。完全透明的图像会原样返回(不裁、不补)。

## 测试约定

- `tests/conftest.py` 的 `pixelate_png_test_params` fixture **硬编码引用 `assets/<name>/<name>.png`**(anchor / ash / bat / blob / demon / mountain / pumpkin)。删改 `assets/` 会让测试失败。

- `tests/test_pixelate.py::test_pixelate_pngs` 是 **视觉回归测试**:断言结果文件存在、尺寸非零、**且 `width == height`**(由 `crop_to_square` 默认开启所保证)。真正的"对错"仍然靠人工肉眼看 `tests/outputs/<name>/`(包含 `edges.png`、`mesh.png` 等中间产物)。改算法后**必须**手动查看输出,光看 `pytest` 绿不算 OK。

- `tests/test_utils.py` 覆盖 `trim_alpha_to_square` 的 7 个 case:全透明、紧密正方形、四面填充、横宽、纵高、奇数填充差(多出的 1 像素去 right/bottom)、alpha 阈值边界(127 排除 / 128 保留)。调裁剪逻辑前先看这些 case。

- 调像素化质量时:先调 `tests/conftest.py` 里对应 case 的 `num_colors`,再跑 `uv run pytest -s tests/test_pixelate.py`,然后看 `tests/outputs/`。这是项目约定的视觉调参流程(`.github/CONTRIBUTING.md`)。

## 贡献规范

提 PR 前 CI 会跑 `ruff check`、`ruff format --check`、`pytest`(Py 3.12/3.13/3.14),全部要绿。注意 `pyproject.toml` 里 `[tool.ruff]` 只启用了 `lint.select = ["I"]`(import 排序),其余规则没启,不要被"ruff 全套"的直觉误导。
