# Filename Size Suffix — Design Spec

**Date:** 2026-05-12
**Related:** Builds on `crop-to-square` (commits `bfec577`, `b70c858`, `b8a93df`).

## Goal

When the pixelation pipeline produces a square output (the `crop_to_square=True`
default), embed the resulting native-pixel resolution in the output filename
(e.g. `bat_pixelated_18x18.png`). The aim is to make file dimensions
immediately visible without `identify`/`exiftool` lookups, useful for
sprite/icon batches and asset libraries.

## Behavior

The size suffix is **coupled to `crop_to_square`**, not exposed as a separate
flag.

| Surface | `crop_to_square` | `-o` mode | Resulting filename |
|---|---|---|---|
| CLI | True (default) | directory or omitted | `<stem>_pixelated_<W>x<H>.png` |
| CLI | True (default) | exact file (`-o out.png`) | `out.png` (unchanged) |
| CLI | False (`--no-square`) | directory or omitted | `<stem>_pixelated.png` (unchanged) |
| CLI | False (`--no-square`) | exact file (`-o out.png`) | `out.png` (unchanged) |
| ppa-gen | True (default) | output dir | `<timestamp>_pixelated_<W>x<H>.png` |
| ppa-gen | False | output dir | `<timestamp>_pixelated.png` |
| Web | True (default) | DownloadButton | `pixelated_<W>x<H>.png` |
| Web | False | DownloadButton | `pixelated.png` |

**Size semantics:** Always `pixelated.size` after the full pipeline runs. In
the typical workflow (`scale_result=1`, the default), this equals the
native pixel-art resolution. If a user passes `--scale-result N > 1`, the
filename honestly reflects the upscaled size (e.g. `_360x360`). This is
acceptable and documented.

**Degenerate input note:** When the input is effectively fully transparent,
`trim_alpha_to_square` short-circuits and returns the input unchanged
(see [utils.py:81-82](proper_pixel_art/utils.py#L81-L82)). In that case
`pixelated.size` is the mesh-cell resolution, not a meaningful "sprite
size". The filename will still get `_<W>x<H>`, but the dimensions reflect
the un-trimmed output. This is a known edge case; the alternative
(suppressing the suffix on degenerate input) would require a signal from
`trim_alpha_to_square`, which adds API surface for a rare case.

**Format:** `_<W>x<H>` — lowercase `x`, underscore separator, placed after
`_pixelated`. Non-square sizes serialize the same way (`_24x18`); the
suffix does not assume `W == H`.

## File-by-File Changes

### `proper_pixel_art/cli.py`

**1. Add a `size_suffix` helper at module level (consumed by CLI, ppa-gen,
and Web — single source of truth for the format).**

```python
def size_suffix(size: tuple[int, int] | None) -> str:
    """Render '_<W>x<H>' for embedding in filenames, or '' if size is None."""
    return f"_{size[0]}x{size[1]}" if size else ""
```

**2. Extend `resolve_output_path` with an optional `size` parameter.**

```python
def resolve_output_path(
    out_path: Path,
    input_path: Path,
    suffix: str = "_pixelated",
    size: tuple[int, int] | None = None,
) -> Path:
    """
    If outpath is a directory, make it a file path
    with filename e.g. (input stem)_pixelated.png, or
    (input stem)_pixelated_18x18.png when size is provided.
    """
    if out_path.suffix:
        return out_path
    filename = f"{input_path.stem}{suffix}{size_suffix(size)}.png"
    return out_path / filename
```

`size=None` preserves legacy behavior. Explicit `-o file.png` (i.e.
`out_path.suffix` truthy) short-circuits before the size logic — explicit
paths are always respected.

**3. Reorder `main()` so `pixelate()` runs before `resolve_output_path`.**

```python
def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path).expanduser()

    img = Image.open(input_path)
    pixelated = pixelate.pixelate(
        img,
        num_colors=args.num_colors,
        scale_result=args.scale_result,
        transparent_background=args.transparent,
        pixel_width=args.pixel_width,
        initial_upscale_factor=args.initial_upscale,
        crop_to_square=args.crop_to_square,
    )

    size = pixelated.size if args.crop_to_square else None
    out_path = resolve_output_path(Path(args.out_path), input_path, size=size)
    out_path.parent.mkdir(exist_ok=True, parents=True)

    pixelated.save(out_path)
```

Side effect: if `pixelate()` raises, the output directory is no longer
pre-created. Neutral reorder, no regression.

### `scripts/ppa_gen.py`

Filenames here are built inline (not via `resolve_output_path`) to keep
ppa-gen's `{timestamp}` naming intact. Import `size_suffix` from `cli` so
the suffix format stays in one place.

Update the existing import:

```python
from proper_pixel_art.cli import add_pixelation_args, size_suffix
```

```python
def process_image(
    original_image: Image.Image,
    args: argparse.Namespace,
    timestamp: str,
    index: int = 0,
) -> tuple[Path, Path]:
    """Pixelate and save a single image."""
    print(f"Processing image {index + 1}...")

    suffix = f"_{index}" if args.n > 1 else ""
    original_filename = f"{timestamp}{suffix}_original.png"
    original_path = args.output_dir / original_filename

    original_image.save(original_path)
    print(f"Saved original: {original_path}")

    print(f"Pixelating image {index + 1}...")
    pixelated_image = pixelate(
        original_image,
        num_colors=args.num_colors,
        initial_upscale_factor=args.initial_upscale,
        scale_result=args.scale_result,
        transparent_background=args.transparent,
        pixel_width=args.pixel_width,
        crop_to_square=args.crop_to_square,
    )

    size = pixelated_image.size if args.crop_to_square else None
    pixelated_filename = f"{timestamp}{suffix}_pixelated{size_suffix(size)}.png"
    pixelated_path = args.output_dir / pixelated_filename

    pixelated_image.save(pixelated_path)
    print(f"Saved pixelated: {pixelated_path}")

    return original_path, pixelated_path
```

`_original.png` is left alone — the original hasn't been cropped, so a
size suffix would be misleading.

### `proper_pixel_art/web.py`

Two additions: a `gr.Markdown` size label, and a `gr.DownloadButton` that
serves a temp file with the proper filename.

**1. Add module-level imports and a shared tempdir** so we don't leak a
fresh `mkdtemp` per pixelation click. One directory per process; the file
inside is overwritten each click.

```python
import tempfile
from pathlib import Path

from PIL import Image

from proper_pixel_art.cli import size_suffix
from proper_pixel_art.pixelate import pixelate

IMG_HEIGHT = 512

_TMP_DIR = Path(tempfile.mkdtemp(prefix="ppa_"))
```

**2. `process` returns a 3-tuple:**

```python
def process(
    image: Image.Image | None,
    num_colors: int,
    transparent: bool,
    scale: int,
    initial_upscale: int,
    pixel_width: int,
    crop_to_square: bool,
):
    """Process image through pixelation pipeline."""
    import gradio as gr

    if image is None:
        return None, "", gr.update(visible=False)

    result = pixelate(
        image,
        num_colors=num_colors if num_colors > 0 else None,
        transparent_background=transparent,
        scale_result=scale if scale > 1 else None,
        initial_upscale_factor=initial_upscale,
        pixel_width=pixel_width if pixel_width > 0 else None,
        crop_to_square=crop_to_square,
    )

    w, h = result.size
    size = result.size if crop_to_square else None
    download_path = _TMP_DIR / f"pixelated{size_suffix(size)}.png"
    result.save(download_path)

    size_text = (
        f"Output size: **{w} × {h}** px"
        if crop_to_square
        else f"Output size: {w} × {h} px (not cropped)"
    )
    btn_label = f"Download {w}×{h}.png" if crop_to_square else "Download.png"
    return (
        result,
        size_text,
        gr.update(value=str(download_path), label=btn_label, visible=True),
    )
```

**3. UI: add a Markdown and a DownloadButton in the output column:**

```python
with gr.Column():
    output_img = gr.Image(
        type="pil",
        label="Output",
        format="png",
        image_mode="RGBA",
        height=IMG_HEIGHT,
        interactive=False,
    )
    output_size = gr.Markdown("")
    output_download = gr.DownloadButton(label="Download", visible=False)
```

**4. `btn.click` outputs the three components:**

```python
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
    outputs=[output_img, output_size, output_download],
)
```

The display label uses U+00D7 (`×`) for visual polish; the **filename** uses
ASCII `x` for Windows safety and grep-ability.

The shared `_TMP_DIR` is created once at module import; subsequent clicks
reuse the same `pixelated{_WxH}.png` path (overwriting). The directory is
left to the OS to reclaim. This matches Gradio's own handling of
transient output files.

### `pyproject.toml`

Pin Gradio ≥ 4.4 in the `[web]` optional dependency group — `gr.DownloadButton`
landed in Gradio 4.4. Without an explicit floor, a fresh install or a stale
lockfile could resolve to an older Gradio and silently break the Download UI.

Change the existing `gradio` entry in the `[project.optional-dependencies]`
table:

```toml
[project.optional-dependencies]
web = [
    "gradio>=4.4",
]
```

(Only the version pin is new; preserve any other entries already in `[web]`.)

### `README.md`

Add a short note in the "Crop to Square" area (or near `--no-square` doc):

> By default, output filenames also embed the cropped resolution:
> `bat_pixelated_18x18.png`. To disable cropping (and the size suffix),
> pass `--no-square`.

### `tests/test_cli.py`

Three unit tests pinning `resolve_output_path`'s contract — they directly
encode acceptance criteria 1–3. `tests/test_cli.py` likely doesn't exist
yet (no CLI-specific tests today); create it if absent, otherwise append.

```python
from pathlib import Path

from proper_pixel_art.cli import resolve_output_path


def test_resolve_output_path_directory_with_size(tmp_path):
    """Directory + size → filename gets _<W>x<H> suffix."""
    result = resolve_output_path(tmp_path, Path("bat.png"), size=(18, 18))
    assert result == tmp_path / "bat_pixelated_18x18.png"


def test_resolve_output_path_directory_no_size(tmp_path):
    """Directory + size=None → legacy filename, no suffix."""
    result = resolve_output_path(tmp_path, Path("bat.png"))
    assert result == tmp_path / "bat_pixelated.png"


def test_resolve_output_path_explicit_file_with_size(tmp_path):
    """Explicit file path always wins — size is ignored."""
    explicit = tmp_path / "out.png"
    result = resolve_output_path(explicit, Path("bat.png"), size=(18, 18))
    assert result == explicit
```

## Out of Scope

- **Manual verification checklist.** The three `resolve_output_path` tests
  pin the spec-critical surface; no separate hand-test doc.
- **CHANGELOG.** Project does not maintain one.
- **`CONTRIBUTING.md`.** No new dev convention.
- **`scripts/README.md`.** ppa-gen inherits CLI semantics; no per-script
  doc update needed.
- **Web `gr.Image` right-click "save" filename.** Out of our control;
  users who want the size-tagged file should use the DownloadButton.

## Acceptance Criteria

1. `resolve_output_path(dir, Path("bat.png"), size=(18, 18))` →
   `dir / "bat_pixelated_18x18.png"`.
2. `resolve_output_path(dir, Path("bat.png"))` →
   `dir / "bat_pixelated.png"` (unchanged from today).
3. `resolve_output_path(Path("out.png"), Path("bat.png"), size=(18, 18))`
   → `Path("out.png")` (explicit path wins).
4. `ppa input.png -o some_dir` (defaults) → file named
   `input_pixelated_<W>x<H>.png` in `some_dir`.
5. `ppa input.png -o some_dir --no-square` → file named
   `input_pixelated.png` in `some_dir` (no size suffix).
6. `ppa-gen --prompt ...` (defaults) → file named
   `<timestamp>_pixelated_<W>x<H>.png` in output dir.
7. `ppa-web` shows an "Output size: W × H px" Markdown line and a
   "Download W×H.png" button after pixelation; clicking the button
   downloads a file literally named `pixelated_<W>x<H>.png`.
8. `uv run pytest tests/test_cli.py` passes on Python 3.12/3.13/3.14
   (matching CI matrix), covering criteria 1–3.
