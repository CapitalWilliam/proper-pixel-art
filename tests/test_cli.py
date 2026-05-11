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
