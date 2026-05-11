# Crop-to-Square Post-Pixelation Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-out post-pixelation step that trims transparent border (alpha < 128) and pads the shorter side with transparent pixels so the final image is square, plumbed through the Python API, CLI, and Gradio web UI.

**Architecture:** A single new pure function `utils.trim_alpha_to_square()` does the cropping and padding. `pixelate.pixelate()` calls it after `make_background_transparent` and before `scale_result`, gated on a new `crop_to_square` parameter (default `True`). CLI exposes `--no-square` to opt out; web UI exposes a checkbox (default checked).

**Tech Stack:** Python 3.12+, PIL (Pillow), pytest, ruff, gradio (web only), argparse (CLI).

**Spec:** `docs/superpowers/specs/2026-05-12-crop-to-square-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `proper_pixel_art/utils.py` | Modify | Add `trim_alpha_to_square()` |
| `proper_pixel_art/pixelate.py` | Modify | Add `crop_to_square` parameter; insert call between `make_background_transparent` and `scale_result` |
| `proper_pixel_art/cli.py` | Modify | Add `--no-square` flag in `add_pixelation_args`; forward in `main()` |
| `scripts/ppa_gen.py` | Modify | Forward `args.crop_to_square` in `process_image` |
| `proper_pixel_art/web.py` | Modify | Add Gradio checkbox + thread param through `process()` |
| `tests/test_utils.py` | Create | Unit tests for `trim_alpha_to_square` |
| `tests/test_pixelate.py` | Modify | Add `width == height` assertion to visual regression test |

---

## Task 1: Implement `utils.trim_alpha_to_square()` (TDD)

**Files:**
- Create: `tests/test_utils.py`
- Modify: `proper_pixel_art/utils.py` (append new function after `scale_img`)

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_utils.py` with the full content below.

```python
"""Tests for utility functions."""

from PIL import Image

from proper_pixel_art import utils


def _make_rgba(
    width: int, height: int, color: tuple[int, int, int, int]
) -> Image.Image:
    """Helper: make an RGBA image of solid color."""
    return Image.new("RGBA", (width, height), color)


class TestTrimAlphaToSquare:
    def test_fully_transparent_returns_unchanged_size(self):
        """Fully transparent image returns input unchanged (size preserved)."""
        img = _make_rgba(10, 6, (0, 0, 0, 0))
        result = utils.trim_alpha_to_square(img)
        assert result.size == (10, 6)
        assert result.mode == "RGBA"

    def test_tight_square_sprite_unchanged(self):
        """Tight square sprite returns unchanged (mode RGBA)."""
        img = _make_rgba(5, 5, (255, 0, 0, 255))
        result = utils.trim_alpha_to_square(img)
        assert result.size == (5, 5)
        assert result.getpixel((0, 0)) == (255, 0, 0, 255)

    def test_padded_sprite_is_cropped_and_squared(self):
        """Sprite with transparent padding on all sides is cropped + padded to square."""
        # 10x10 canvas with opaque 4x2 sprite at x=3..6, y=4..5
        img = _make_rgba(10, 10, (0, 0, 0, 0))
        for x in range(3, 7):
            for y in range(4, 6):
                img.putpixel((x, y), (0, 255, 0, 255))
        result = utils.trim_alpha_to_square(img)
        # Tight bbox is 4x2; padded to 4x4 square
        assert result.size == (4, 4)
        # Vertically centered: row 0 transparent, rows 1-2 sprite, row 3 transparent
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((0, 1)) == (0, 255, 0, 255)
        assert result.getpixel((0, 2)) == (0, 255, 0, 255)
        assert result.getpixel((0, 3))[3] == 0

    def test_wider_than_tall_pads_vertically(self):
        """Wider-than-tall content adds vertical padding evenly top/bottom."""
        img = _make_rgba(10, 10, (0, 0, 0, 0))
        # 6x2 sprite at x=2..7, y=4..5
        for x in range(2, 8):
            for y in range(4, 6):
                img.putpixel((x, y), (255, 0, 0, 255))
        result = utils.trim_alpha_to_square(img)
        assert result.size == (6, 6)
        # Top 2 rows transparent, middle 2 rows sprite, bottom 2 rows transparent
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((0, 1))[3] == 0
        assert result.getpixel((0, 2)) == (255, 0, 0, 255)
        assert result.getpixel((0, 5))[3] == 0

    def test_taller_than_wide_pads_horizontally(self):
        """Taller-than-wide content adds horizontal padding evenly left/right."""
        img = _make_rgba(10, 10, (0, 0, 0, 0))
        # 2x6 sprite at x=4..5, y=2..7
        for x in range(4, 6):
            for y in range(2, 8):
                img.putpixel((x, y), (0, 0, 255, 255))
        result = utils.trim_alpha_to_square(img)
        assert result.size == (6, 6)
        # Left 2 cols transparent, middle 2 cols sprite, right 2 cols transparent
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((1, 0))[3] == 0
        assert result.getpixel((2, 0)) == (0, 0, 255, 255)
        assert result.getpixel((5, 0))[3] == 0

    def test_odd_padding_deficit_extra_on_trailing_side(self):
        """Odd padding deficit places extra pixel on the trailing (bottom) side."""
        # 3x2 sprite at x=1..3, y=1..2 — vertical deficit is 1
        img = _make_rgba(5, 5, (0, 0, 0, 0))
        for x in range(1, 4):
            for y in range(1, 3):
                img.putpixel((x, y), (128, 128, 128, 255))
        result = utils.trim_alpha_to_square(img)
        # Tight bbox 3x2; padded to 3x3; pad_top=0, pad_bottom=1
        assert result.size == (3, 3)
        # Top row should be sprite (no pad on top)
        assert result.getpixel((0, 0)) == (128, 128, 128, 255)
        # Bottom row should be transparent (extra pad on bottom)
        assert result.getpixel((0, 2))[3] == 0

    def test_alpha_threshold_boundary(self):
        """Alpha exactly at threshold (128) included; just below (127) excluded."""
        img = _make_rgba(5, 5, (0, 0, 0, 0))
        # alpha=127 — should be excluded
        img.putpixel((1, 1), (255, 0, 0, 127))
        # alpha=128 — should be included
        img.putpixel((3, 3), (0, 255, 0, 128))
        result = utils.trim_alpha_to_square(img)
        # Only the alpha=128 pixel counts; bbox is 1x1, padded to 1x1
        assert result.size == (1, 1)
        assert result.getpixel((0, 0)) == (0, 255, 0, 128)
```

- [ ] **Step 1.2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_utils.py -v`
Expected: All 7 tests FAIL with `AttributeError: module 'proper_pixel_art.utils' has no attribute 'trim_alpha_to_square'`.

- [ ] **Step 1.3: Implement `trim_alpha_to_square` in `utils.py`**

Append the function (and an import for `RGBA` tuple) to `proper_pixel_art/utils.py` — add it AFTER the existing `scale_img` function. The file already imports `Image` so no new top-level imports are needed.

```python
def trim_alpha_to_square(
    image: Image.Image,
    alpha_threshold: int = 128,
) -> Image.Image:
    """
    Crop the transparent border (alpha < threshold) of an image,
    then pad the shorter side with fully transparent pixels so the
    result is square. Sprite stays visually centered; if the padding
    deficit is odd the extra pixel goes on the right/bottom.

    If no pixel meets the alpha threshold (image is effectively
    fully transparent), returns the input unchanged (as an RGBA copy).
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    # Binary mask: 255 where alpha >= threshold, 0 elsewhere
    mask = alpha.point(lambda p: 255 if p >= alpha_threshold else 0)
    bbox = mask.getbbox()

    if bbox is None:
        return rgba.copy()

    cropped = rgba.crop(bbox)
    w, h = cropped.size
    if w == h:
        return cropped

    side = max(w, h)
    pad_w = side - w
    pad_h = side - h
    pad_left = pad_w // 2
    pad_top = pad_h // 2

    result = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    result.paste(cropped, (pad_left, pad_top))
    return result
```

- [ ] **Step 1.4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_utils.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 1.5: Ruff lint + format**

Run:
```bash
uv run ruff format proper_pixel_art/utils.py tests/test_utils.py
uv run ruff check proper_pixel_art/utils.py tests/test_utils.py
```
Expected: format reports no changes (or applies them); `ruff check` exits 0.

- [ ] **Step 1.6: Commit**

```bash
git add proper_pixel_art/utils.py tests/test_utils.py
git commit -m "feat(utils): add trim_alpha_to_square helper

Crops transparent border (alpha < 128) and pads the shorter side
with transparent pixels so the result is square, sprite centered.
Returns the input unchanged when the image is fully transparent."
```

---

## Task 2: Wire `trim_alpha_to_square` into `pixelate()` (default on)

**Files:**
- Modify: `proper_pixel_art/pixelate.py` (function `pixelate()`, signature + final block)
- Modify: `tests/test_pixelate.py` (add `width == height` assertion)

- [ ] **Step 2.1: Update the visual regression test to assert squareness**

In `tests/test_pixelate.py`, the existing loop already does `assert result.width > 0 and result.height > 0`. Add a square assertion right after it. The full updated test body should look like this — replace the existing loop body with this version:

```python
def test_pixelate_pngs(pixelate_png_test_params: dict[str, dict]) -> None:
    """Test that pixelate algorithm runs without error for png images and generates output."""
    output_dir = Path.cwd() / "tests" / "outputs"
    output_dir.mkdir(exist_ok=True, parents=True)
    for name, params in pixelate_png_test_params.items():
        pixel_dir = output_dir / str(name)
        pixel_dir.mkdir(parents=True, exist_ok=True)

        img = Image.open(params["path"])

        # Pixelate
        result = pixelate.pixelate(
            img,
            num_colors=params["num_colors"],
            scale_result=params["result_scale"],
            transparent_background=params["transparent_background"],
            intermediate_dir=pixel_dir,
        )

        # Save the result
        result_path = pixel_dir / "result.png"
        result.save(result_path)

        # Verify the output exists and has a width and height
        assert result_path.exists(), f"Output file not created for {name}"
        assert result.width > 0 and result.height > 0, f"Invalid dimensions for {name}"
        assert result.width == result.height, f"Output not square for {name}"

        print(f"Generated output for {name}: {result_path}")
    print(
        (
            "Successfully generated all .png test images.\n"
            f"Manually inspect the results in {output_dir} to verify pixelation quality."
        )
    )
```

- [ ] **Step 2.2: Run the visual regression test to verify it fails**

Run: `uv run pytest tests/test_pixelate.py -v`
Expected: FAIL with `AssertionError: Output not square for <name>` on at least one of the asset cases (e.g., `bat`, `pumpkin`).

- [ ] **Step 2.3: Add `crop_to_square` parameter and call site in `pixelate()`**

Open `proper_pixel_art/pixelate.py`. Make the changes below to the `pixelate` function ONLY — leave `downsample` untouched.

Change the signature from:

```python
def pixelate(
    image: Image.Image,
    num_colors: int | None = None,
    initial_upscale_factor: int = 2,
    scale_result: int | None = None,
    transparent_background: bool = False,
    intermediate_dir: Path | None = None,
    pixel_width: int | None = None,
) -> Image.Image:
```

to:

```python
def pixelate(
    image: Image.Image,
    num_colors: int | None = None,
    initial_upscale_factor: int = 2,
    scale_result: int | None = None,
    transparent_background: bool = False,
    intermediate_dir: Path | None = None,
    pixel_width: int | None = None,
    crop_to_square: bool = True,
) -> Image.Image:
```

And update the docstring's parameter list — append after the existing `pixel_width` entry:

```
    - crop_to_square:
        If True (default), trim the transparent border of the result and
        pad the shorter side with transparent pixels so the output is square.
```

Then update the final block of the function. Replace:

```python
    if transparent_background:
        result = colors.make_background_transparent(result)

    if scale_result is not None:
        result = utils.scale_img(result, int(scale_result))

    return result
```

with:

```python
    if transparent_background:
        result = colors.make_background_transparent(result)

    if crop_to_square:
        result = utils.trim_alpha_to_square(result)

    if scale_result is not None:
        result = utils.scale_img(result, int(scale_result))

    return result
```

- [ ] **Step 2.4: Run the visual regression test to verify it passes**

Run: `uv run pytest tests/test_pixelate.py -v`
Expected: PASS.

- [ ] **Step 2.5: Run the full test suite to verify nothing else broke**

Run: `uv run pytest -v`
Expected: All tests in `test_utils.py`, `test_mesh.py`, `test_colors.py`, `test_pixelate.py` PASS.

- [ ] **Step 2.6: Manually inspect a few outputs**

Run: `uv run pytest -s tests/test_pixelate.py` and open `tests/outputs/bat/result.png` and `tests/outputs/pumpkin/result.png` in an image viewer. Verify each result is square and the sprite is centered.

- [ ] **Step 2.7: Ruff lint + format**

Run:
```bash
uv run ruff format proper_pixel_art/pixelate.py tests/test_pixelate.py
uv run ruff check proper_pixel_art/pixelate.py tests/test_pixelate.py
```

- [ ] **Step 2.8: Commit**

```bash
git add proper_pixel_art/pixelate.py tests/test_pixelate.py
git commit -m "feat(pixelate): crop output to square by default

Adds a crop_to_square parameter (default True) that trims the
transparent border and pads the shorter side with transparent
pixels. Runs after make_background_transparent so generated
transparency is included, and before scale_result so the bbox
is measured at true pixel resolution.

The visual regression test now asserts every output is square."
```

---

## Task 3: Expose `--no-square` flag in the CLI and `ppa-gen` script

**Files:**
- Modify: `proper_pixel_art/cli.py` (function `add_pixelation_args`, function `main`)
- Modify: `scripts/ppa_gen.py` (function `process_image`)

- [ ] **Step 3.1: Add `--no-square` to `add_pixelation_args`**

Open `proper_pixel_art/cli.py`. Inside `add_pixelation_args`, append this argument just before the final `return parser`:

```python
    pixel_group.add_argument(
        "--no-square",
        dest="crop_to_square",
        action="store_false",
        default=True,
        help="Disable trim-to-bbox and pad-to-square on the output (default: enabled).",
    )
```

- [ ] **Step 3.2: Forward `crop_to_square` from `main()` in `cli.py`**

In `proper_pixel_art/cli.py::main`, replace the call:

```python
    pixelated = pixelate.pixelate(
        img,
        num_colors=args.num_colors,
        scale_result=args.scale_result,
        transparent_background=args.transparent,
        pixel_width=args.pixel_width,
        initial_upscale_factor=args.initial_upscale,
    )
```

with:

```python
    pixelated = pixelate.pixelate(
        img,
        num_colors=args.num_colors,
        scale_result=args.scale_result,
        transparent_background=args.transparent,
        pixel_width=args.pixel_width,
        initial_upscale_factor=args.initial_upscale,
        crop_to_square=args.crop_to_square,
    )
```

- [ ] **Step 3.3: Forward `crop_to_square` from `process_image` in `ppa_gen.py`**

Open `scripts/ppa_gen.py`. In `process_image`, replace the call:

```python
    pixelated_image = pixelate(
        original_image,
        num_colors=args.num_colors,
        initial_upscale_factor=args.initial_upscale,
        scale_result=args.scale_result,
        transparent_background=args.transparent,
        pixel_width=args.pixel_width,
    )
```

with:

```python
    pixelated_image = pixelate(
        original_image,
        num_colors=args.num_colors,
        initial_upscale_factor=args.initial_upscale,
        scale_result=args.scale_result,
        transparent_background=args.transparent,
        pixel_width=args.pixel_width,
        crop_to_square=args.crop_to_square,
    )
```

- [ ] **Step 3.4: Smoke test the CLI on an existing asset**

Run two ad-hoc CLI invocations into a scratch directory, then open both PNGs in an image viewer.

```bash
mkdir -p tests/outputs/_smoke
uv run ppa assets/bat/bat.png -o tests/outputs/_smoke/bat_square.png -c 16 -s 5 -t
uv run ppa assets/bat/bat.png -o tests/outputs/_smoke/bat_unchanged.png -c 16 -s 5 -t --no-square
```

Expected: `bat_square.png` has `width == height`; `bat_unchanged.png` is non-square (`width != height`).

- [ ] **Step 3.5: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 3.6: Ruff lint + format**

Run:
```bash
uv run ruff format proper_pixel_art/cli.py scripts/ppa_gen.py
uv run ruff check proper_pixel_art/cli.py scripts/ppa_gen.py
```

- [ ] **Step 3.7: Commit**

```bash
git add proper_pixel_art/cli.py scripts/ppa_gen.py
git commit -m "feat(cli): expose --no-square flag

Adds the opt-out switch to the shared add_pixelation_args so both
ppa and ppa-gen pick it up automatically. Default behavior is to
crop+square the output."
```

---

## Task 4: Expose `Crop to Square` checkbox in the Gradio web UI

**Files:**
- Modify: `proper_pixel_art/web.py` (function `process` signature + body, function `create_demo`)

- [ ] **Step 4.1: Update `process()` to accept and forward `crop_to_square`**

Open `proper_pixel_art/web.py`. Replace the entire `process` function with:

```python
def process(
    image: Image.Image | None,
    num_colors: int,
    transparent: bool,
    scale: int,
    initial_upscale: int,
    pixel_width: int,
    crop_to_square: bool,
) -> Image.Image | None:
    """Process image through pixelation pipeline."""
    if image is None:
        return None
    return pixelate(
        image,
        num_colors=num_colors if num_colors > 0 else None,
        transparent_background=transparent,
        scale_result=scale if scale > 1 else None,
        initial_upscale_factor=initial_upscale,
        pixel_width=pixel_width if pixel_width > 0 else None,
        crop_to_square=crop_to_square,
    )
```

- [ ] **Step 4.2: Add the checkbox in `create_demo()` and wire it through `btn.click`**

In `proper_pixel_art/web.py::create_demo`, replace the final controls row + click handler. The current code reads:

```python
        with gr.Row():
            transparent = gr.Checkbox(value=False, label="Transparent Background")
            btn = gr.Button("Pixelate", variant="primary")

        btn.click(
            fn=process,
            inputs=[
                input_img,
                num_colors,
                transparent,
                scale,
                initial_upscale,
                pixel_width,
            ],
            outputs=output_img,
        )
```

Replace with:

```python
        with gr.Row():
            transparent = gr.Checkbox(value=False, label="Transparent Background")
            crop_to_square = gr.Checkbox(value=True, label="Crop to Square")
            btn = gr.Button("Pixelate", variant="primary")

        btn.click(
            fn=process,
            inputs=[
                input_img,
                num_colors,
                transparent,
                scale,
                initial_upscale,
                pixel_width,
                crop_to_square,
            ],
            outputs=output_img,
        )
```

- [ ] **Step 4.3: Smoke test the web UI manually**

Run:
```bash
uv sync --extra web
uv run ppa-web
```

Open http://127.0.0.1:7860. Upload `assets/bat/bat.png`, click **Pixelate** with **Crop to Square** checked — verify the output is square. Uncheck it and re-run — verify the output is not square.

- [ ] **Step 4.4: Ruff lint + format**

Run:
```bash
uv run ruff format proper_pixel_art/web.py
uv run ruff check proper_pixel_art/web.py
```

- [ ] **Step 4.5: Run the full test suite one final time**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 4.6: Commit**

```bash
git add proper_pixel_art/web.py
git commit -m "feat(web): add Crop to Square checkbox

Default-checked toggle next to Transparent Background, threaded
through process() to pixelate(crop_to_square=...)."
```

---

## Self-Review Notes

- **Spec coverage:** Every section of the spec is implemented:
  - `trim_alpha_to_square()` API + behavior contract → Task 1
  - `crop_to_square: bool = True` parameter in `pixelate()` → Task 2
  - Insertion ordering (after `make_background_transparent`, before `scale_result`) → Task 2
  - `--no-square` CLI flag in `add_pixelation_args` → Task 3
  - Forwarding in `cli.py::main` and `scripts/ppa_gen.py::process_image` → Task 3
  - Gradio `Crop to Square` checkbox → Task 4
  - All seven unit-test scenarios → Task 1, Step 1.1
  - `width == height` assertion in visual regression → Task 2, Step 2.1
- **Naming consistency:** `crop_to_square` is the parameter name used in every call site (API, CLI dest, ppa-gen forward, web UI). The CLI surface is `--no-square` (`store_false`); the dest is `crop_to_square`.
- **No placeholders:** All test bodies, function bodies, signatures, and commit messages are written out in full.
