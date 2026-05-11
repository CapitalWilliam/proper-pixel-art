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
        assert result.mode == "RGBA"
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
