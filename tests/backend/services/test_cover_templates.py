from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from backend.app.schemas.local_metadata import LocalCoverPreviewRequest
from backend.app.services.cover_templates import (
    CoverTemplateError,
    _font,
    _line_width,
    _resolve_title_font_id,
    _wrap_text,
    generate_cover_previews,
)


def test_cover_preview_request_accepts_bounded_title_controls_defaults() -> None:
    default_request = LocalCoverPreviewRequest(
        video_path=Path("/media/source.mp4"),
        title="Poster Title",
    )
    customized_request = LocalCoverPreviewRequest(
        video_path=Path("/media/source.mp4"),
        title="Poster Title",
        title_angle_degrees=-15,
        title_position_x_percent=25,
        title_position_y_percent=80,
    )

    assert default_request.title_angle_degrees == 0.0
    assert default_request.title_position_x_percent is None
    assert default_request.title_position_y_percent is None
    assert default_request.title_font_id is None
    assert customized_request.title_angle_degrees == -15
    assert customized_request.title_position_x_percent == 25
    assert customized_request.title_position_y_percent == 80
    assert LocalCoverPreviewRequest(
        video_path=Path("/media/source.mp4"),
        title="Poster Title",
        title_font_id="smiley_sans",
    ).title_font_id == "smiley_sans"
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_angle_degrees=25,
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_position_x_percent=-1,
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_position_y_percent=101,
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_font_id="unknown_font",
        )


def test_template_defaults_are_only_default_title_fonts() -> None:
    assert _resolve_title_font_id("simple_poster", None) == "source_han_sans"
    assert _resolve_title_font_id("jav_classic_left_strip", None) == "dela_gothic_one"
    assert _resolve_title_font_id("tangxin_vlog", None) == "smiley_sans"
    assert _resolve_title_font_id("tangxin_vlog", "lxgw_wenkai") == "lxgw_wenkai"
    with pytest.raises(CoverTemplateError, match="unknown_poster_font"):
        _resolve_title_font_id("simple_poster", "unknown_font")  # type: ignore[arg-type]


def test_title_wrapping_preserves_manual_line_breaks() -> None:
    font = _font(36)
    max_width = _line_width("Manual First Line", font) + 20

    lines = _wrap_text(
        "Manual First Line\nSecond Line With Extra Words",
        font,
        max_width=max_width,
        max_lines=3,
    )

    assert lines[0] == "Manual First Line"
    assert len(lines) == 3
    assert lines[1].startswith("Second")


def test_title_angle_changes_cover_cache_key_and_poster_render(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", (640, 360), (120, 84, 48)).save(frame_path)

    flat = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=0,
        template="simple_poster",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )
    flat_poster = flat.poster_path.read_bytes()
    flat_fanart = flat.fanart_path.read_bytes()

    tilted = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=-10,
        template="simple_poster",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )

    assert flat.poster_path != tilted.poster_path
    assert flat.fanart_path == tilted.fanart_path
    assert flat_poster != tilted.poster_path.read_bytes()
    assert flat_fanart == tilted.fanart_path.read_bytes()

    retitled = generate_cover_previews(
        title="Changed Poster Title",
        title_angle_degrees=-10,
        template="simple_poster",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )

    assert tilted.poster_path != retitled.poster_path
    assert tilted.fanart_path == retitled.fanart_path


def test_title_position_changes_poster_cache_key_and_render_only(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", (640, 360), (120, 84, 48)).save(frame_path)

    default_position = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=0,
        template="simple_poster",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )
    default_poster = default_position.poster_path.read_bytes()
    default_fanart = default_position.fanart_path.read_bytes()

    moved_position = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=0,
        title_position_x_percent=10,
        title_position_y_percent=10,
        template="simple_poster",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )

    assert default_position.poster_path != moved_position.poster_path
    assert default_position.fanart_path == moved_position.fanart_path
    assert default_poster != moved_position.poster_path.read_bytes()
    assert default_fanart == moved_position.fanart_path.read_bytes()


def test_title_font_changes_poster_cache_key_but_not_fanart(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", (640, 360), (120, 84, 48)).save(frame_path)

    default_font = generate_cover_previews(
        title="Manual\nPoster Title",
        template="tangxin_vlog",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )
    override_font = generate_cover_previews(
        title="Manual\nPoster Title",
        template="tangxin_vlog",
        title_font_id="lxgw_wenkai",
        frame_paths=[frame_path],
        output_dir=tmp_path / "covers",
    )

    assert default_font.title_font_id == "smiley_sans"
    assert override_font.title_font_id == "lxgw_wenkai"
    assert "tangxin_vlog-smiley_sans" in default_font.poster_path.name
    assert "tangxin_vlog-lxgw_wenkai" in override_font.poster_path.name
    assert default_font.poster_path != override_font.poster_path
    assert default_font.fanart_path == override_font.fanart_path
