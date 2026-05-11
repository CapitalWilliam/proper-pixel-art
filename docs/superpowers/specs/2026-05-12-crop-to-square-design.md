# Crop output to square via transparent-alpha bounding box

**Status:** Approved (2026-05-12)
**Scope:** Add a post-pixelation step that trims transparent padding off the result and pads the shorter side with transparent pixels so the final image is square.

## Motivation

Input images to `proper-pixel-art` frequently come with large transparent canvas around the sprite (e.g. Pokémon screenshots, GPT-4o sprite outputs). The current pipeline preserves whatever canvas the user supplied, so the pixelated output inherits the same wasteful padding. Trimming and re-padding to a square gives downstream tools (sprite atlases, game engines, icon use) a tight, predictable asset.

## Behavior

After the existing pixelation pipeline produces the final RGBA result, apply:

1. Compute the bounding box of pixels whose alpha is at or above `ALPHA_THRESHOLD` (128, same constant the rest of the codebase uses).
2. Crop the image to that bounding box.
3. If the cropped image is not square, pad the shorter side **symmetrically** with fully transparent pixels `(0, 0, 0, 0)` so the result is square and the sprite stays visually centered. When the deficit is odd, the extra pixel goes on the right/bottom (`ceil` on the trailing side).
4. If no pixel meets the alpha threshold (entirely transparent image), return the input unchanged — zero behavior, no crash.

The feature is enabled by default and can be turned off explicitly.

## API surface

### New utility — `proper_pixel_art/utils.py`

```python
def trim_alpha_to_square(
    image: Image.Image,
    alpha_threshold: int = 128,
) -> Image.Image:
    """Crop transparent border (alpha < threshold) then pad short side
    with transparent pixels to make the result square."""
```

Behavior contract:

- Input may be any mode; function converts to RGBA internally.
- Output is RGBA.
- If `getbbox()` of the alpha-thresholded mask returns `None`, return a copy of the input unchanged.
- Output is square: `result.width == result.height`.

### Pipeline integration — `proper_pixel_art/pixelate.py::pixelate()`

Add a new parameter:

```python
def pixelate(
    image: Image.Image,
    num_colors: int | None = None,
    initial_upscale_factor: int = 2,
    scale_result: int | None = None,
    transparent_background: bool = False,
    intermediate_dir: Path | None = None,
    pixel_width: int | None = None,
    crop_to_square: bool = True,   # new
) -> Image.Image:
```

Insertion point inside `pixelate()` — after `make_background_transparent`, before `scale_result`:

```
result = downsample(...)
if transparent_background:
    result = colors.make_background_transparent(result)
if crop_to_square:
    result = utils.trim_alpha_to_square(result)   # new
if scale_result is not None:
    result = utils.scale_img(result, int(scale_result))
return result
```

Rationale for ordering:

- **After `make_background_transparent`** so transparent pixels produced by that step are included in the trim.
- **Before `scale_result`** so the bbox is computed on the true-pixel-resolution result, not the upscaled one. This keeps the trim deterministic and avoids subtle off-by-N pixels from nearest-neighbor upscaling.

### CLI — `proper_pixel_art/cli.py::add_pixelation_args()`

Add inside `add_pixelation_args` (so `ppa` and `ppa-gen` both get it):

```python
pixel_group.add_argument(
    "--no-square",
    dest="crop_to_square",
    action="store_false",
    default=True,
    help="Disable trim-to-bbox and pad-to-square on the output (default: enabled).",
)
```

And forward it through `main()` to `pixelate(..., crop_to_square=args.crop_to_square)`. Same wiring change in `scripts/ppa_gen.py::process_image`.

### Web UI — `proper_pixel_art/web.py`

Add a `gr.Checkbox(value=True, label="Crop to Square")` next to the existing `Transparent Background` checkbox. Wire it through `process()` to `pixelate(..., crop_to_square=crop_to_square)`.

## Edge cases

| Case | Behavior |
|---|---|
| Fully transparent image | Return input unchanged (no crash, no division by zero). |
| Already-square tight image | No-op other than mode normalization to RGBA. |
| 1-row or 1-column visible content | Pad to N×N where N = max(w, h). |
| RGB input (no alpha channel) | Function converts to RGBA; all pixels are opaque so bbox is the full image → returned as-is square-padded if needed. |
| Odd-sized padding deficit | Extra pixel goes on right/bottom. |

## Testing

### New unit tests — `tests/test_utils.py` (new file)

Test cases for `trim_alpha_to_square`:

1. Fully transparent image → returned unchanged.
2. Tight square sprite, no padding → returned unchanged (mode RGBA).
3. Sprite with transparent padding on all sides → cropped to bbox, padded to square, sprite centered.
4. Wider-than-tall sprite → vertical pad added evenly top/bottom.
5. Taller-than-wide sprite → horizontal pad added evenly left/right.
6. Odd padding deficit → extra pixel on trailing side (right or bottom).
7. Alpha right at threshold (alpha=127 vs 128) → 127 excluded, 128 included.

### Visual regression — `tests/test_pixelate.py`

The existing `test_pixelate_pngs` already runs the full pipeline on the assets. After this change, every `tests/outputs/<name>/result.png` must be square. Add a simple assertion alongside the existing "exists / non-zero size" checks:

```python
assert result.width == result.height, f"Output not square for {name}"
```

This makes the visual regression also enforce the new contract.

### Manual inspection

Per `.github/CONTRIBUTING.md`, after running tests verify `tests/outputs/<name>/result.png` looks correct — sprite centered, transparent margins symmetric.

## Out of scope

- Padding color other than fully transparent (always `(0,0,0,0)`).
- Non-symmetric padding biased to one side.
- Cropping to non-square aspect ratios (1:1 fixed).
- Cropping the **input** image before pixelation (the user explicitly chose post-pixelation timing in brainstorming).
- A separate stand-alone CLI to crop arbitrary PNGs (only integrated into the pixelate pipeline).
