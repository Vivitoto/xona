from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from backend.app.schemas.local_metadata import LocalCoverPreviewRequest
from backend.app.services.cover_templates import (
    FANART_SIZE,
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
        title_font_size=92,
        title_fill_color="#f8fafc",
        title_stroke_color="#111827",
        title_stroke_width=5,
        title_effect="glow",
    )

    assert default_request.title_angle_degrees == 0.0
    assert default_request.title_position_x_percent is None
    assert default_request.title_position_y_percent is None
    assert default_request.title_font_id is None
    assert default_request.title_font_size is None
    assert default_request.title_fill_color is None
    assert default_request.title_stroke_color is None
    assert default_request.title_stroke_width is None
    assert default_request.title_effect is None
    assert customized_request.title_angle_degrees == -15
    assert customized_request.title_position_x_percent == 25
    assert customized_request.title_position_y_percent == 80
    assert customized_request.title_font_size == 92
    assert customized_request.title_fill_color == "#f8fafc"
    assert customized_request.title_stroke_color == "#111827"
    assert customized_request.title_stroke_width == 5
    assert customized_request.title_effect == "glow"
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
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_font_size=8,
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_fill_color="white",
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_stroke_color="#12345g",
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_stroke_width=32,
        )
    with pytest.raises(ValidationError):
        LocalCoverPreviewRequest(
            video_path=Path("/media/source.mp4"),
            title="Poster Title",
            title_effect="outline",
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
    assert len(lines) >= 3
    assert lines[1].startswith("Second")
    assert all("..." not in line for line in lines)


def test_title_wrapping_does_not_ellipsize_when_wrapping_past_soft_line_limit() -> None:
    font = _font(40)
    max_width = _line_width("Manual", font) + 10

    lines = _wrap_text(
        "Manual Poster Title With Many Words",
        font,
        max_width=max_width,
        max_lines=2,
    )

    assert len(lines) > 2
    assert all("..." not in line for line in lines)


def test_cover_templates_skip_low_quality_frames_when_enough_good_frames_exist(
    tmp_path: Path,
) -> None:
    low_quality = [
        _solid_frame(tmp_path / "black.jpg", (0, 0, 0)),
        _solid_frame(tmp_path / "white.jpg", (255, 255, 255)),
        _solid_frame(tmp_path / "flat.jpg", (120, 120, 120)),
    ]
    good_frames = [
        _pattern_frame(tmp_path / f"good-{index}.jpg", color)
        for index, color in enumerate(_nine_colors(), start=1)
    ]

    generated = generate_cover_previews(
        title="Quality Selected Title",
        template="simple_poster",
        frame_paths=[*low_quality, *good_frames],
        output_dir=tmp_path / "quality",
    )

    with Image.open(generated.thumb_path) as thumb:
        tile_width = FANART_SIZE[0] // 3
        tile_height = FANART_SIZE[1] // 3
        sampled = [
            thumb.getpixel(
                (
                    (index % 3) * tile_width + tile_width // 2,
                    (index // 3) * tile_height + tile_height // 2,
                )
            )
            for index in range(9)
        ]

    assert all(sum(pixel) > 30 for pixel in sampled)
    assert all(sum(pixel) < 735 for pixel in sampled)


def test_cover_templates_treat_content_duplicates_as_not_distinct(tmp_path: Path) -> None:
    frame_paths = [
        _pattern_frame(tmp_path / f"unique-{index}.jpg", color)
        for index, color in enumerate(_nine_colors()[:8], start=1)
    ]
    duplicate = tmp_path / "duplicate-copy.jpg"
    duplicate.write_bytes(frame_paths[0].read_bytes())

    with pytest.raises(CoverTemplateError, match="nine_distinct_frames_required:8"):
        generate_cover_previews(
            title="Duplicate Content Title",
            template="simple_poster",
            frame_paths=[*frame_paths, duplicate],
            output_dir=tmp_path / "duplicates",
        )


def test_jav_fanart_main_image_occupies_exact_right_half(tmp_path: Path) -> None:
    frame_paths = _nine_frame_paths(tmp_path)

    generated = generate_cover_previews(
        title="JAV Classic Title",
        template="jav_classic_left_strip",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )

    with Image.open(generated.fanart_path) as fanart:
        assert fanart.size == FANART_SIZE
        assert _near_color(fanart.getpixel((960, 120)), (120, 84, 48))
        assert _near_color(fanart.getpixel((FANART_SIZE[0] - 120, 120)), (120, 84, 48))
        assert not _near_color(fanart.getpixel((959, 120)), (120, 84, 48))


def test_title_angle_changes_cover_cache_key_and_artwork_render(tmp_path: Path) -> None:
    frame_paths = _nine_frame_paths(tmp_path)

    flat = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=0,
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )
    flat_poster = flat.poster_path.read_bytes()
    flat_fanart = flat.fanart_path.read_bytes()
    flat_thumb = flat.thumb_path.read_bytes()

    tilted = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=-10,
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )

    assert flat.poster_path != tilted.poster_path
    assert flat.fanart_path != tilted.fanart_path
    assert flat.thumb_path == tilted.thumb_path
    assert flat_poster != tilted.poster_path.read_bytes()
    assert flat_fanart != tilted.fanart_path.read_bytes()
    assert flat_thumb == tilted.thumb_path.read_bytes()

    retitled = generate_cover_previews(
        title="Changed Poster Title",
        title_angle_degrees=-10,
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )

    assert tilted.poster_path != retitled.poster_path
    assert tilted.fanart_path != retitled.fanart_path
    assert tilted.thumb_path == retitled.thumb_path


def test_title_position_changes_cover_cache_key_and_artwork_render(tmp_path: Path) -> None:
    frame_paths = _nine_frame_paths(tmp_path)

    default_position = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=0,
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )
    default_poster = default_position.poster_path.read_bytes()
    default_fanart = default_position.fanart_path.read_bytes()
    default_thumb = default_position.thumb_path.read_bytes()

    moved_position = generate_cover_previews(
        title="Manual\nPoster Title",
        title_angle_degrees=0,
        title_position_x_percent=10,
        title_position_y_percent=10,
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )

    assert default_position.poster_path != moved_position.poster_path
    assert default_position.fanart_path != moved_position.fanart_path
    assert default_position.thumb_path == moved_position.thumb_path
    assert default_poster != moved_position.poster_path.read_bytes()
    assert default_fanart != moved_position.fanart_path.read_bytes()
    assert default_thumb == moved_position.thumb_path.read_bytes()


def test_title_font_changes_cover_cache_key_but_not_thumb(tmp_path: Path) -> None:
    frame_paths = _nine_frame_paths(tmp_path)

    default_font = generate_cover_previews(
        title="Manual\nPoster Title",
        template="tangxin_vlog",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )
    override_font = generate_cover_previews(
        title="Manual\nPoster Title",
        template="tangxin_vlog",
        title_font_id="lxgw_wenkai",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )

    assert default_font.title_font_id == "smiley_sans"
    assert override_font.title_font_id == "lxgw_wenkai"
    assert "tangxin_vlog-smiley_sans" in default_font.poster_path.name
    assert "tangxin_vlog-lxgw_wenkai" in override_font.poster_path.name
    assert default_font.poster_path != override_font.poster_path
    assert default_font.fanart_path != override_font.fanart_path
    assert default_font.thumb_path == override_font.thumb_path


def test_title_style_controls_change_cover_cache_key_and_artwork_render(
    tmp_path: Path,
) -> None:
    frame_paths = _nine_frame_paths(tmp_path)

    default_style = generate_cover_previews(
        title="Manual\nPoster Title",
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )
    default_poster = default_style.poster_path.read_bytes()
    default_fanart = default_style.fanart_path.read_bytes()
    default_thumb = default_style.thumb_path.read_bytes()

    custom_style = generate_cover_previews(
        title="Manual\nPoster Title",
        template="simple_poster",
        title_font_size=52,
        title_fill_color="#f8fafc",
        title_stroke_color="#e11d48",
        title_stroke_width=0,
        title_effect="none",
        frame_paths=frame_paths,
        output_dir=tmp_path / "covers",
    )

    assert default_style.poster_path != custom_style.poster_path
    assert default_style.fanart_path != custom_style.fanart_path
    assert default_style.thumb_path == custom_style.thumb_path
    assert default_poster != custom_style.poster_path.read_bytes()
    assert default_fanart != custom_style.fanart_path.read_bytes()
    assert default_thumb == custom_style.thumb_path.read_bytes()


def _nine_frame_paths(tmp_path: Path) -> list[Path]:
    colors = [
        (120, 84, 48),
        (190, 80, 80),
        (80, 150, 90),
        (70, 100, 190),
        (210, 170, 60),
        (140, 80, 190),
        (60, 165, 180),
        (220, 95, 150),
        (90, 95, 105),
    ]
    paths: list[Path] = []
    for index, color in enumerate(colors, start=1):
        path = tmp_path / f"frame-{index}.jpg"
        Image.new("RGB", (640, 360), color).save(path)
        paths.append(path)
    return paths


def _solid_frame(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), color)
    image.save(path, "JPEG", quality=95)
    return path


def _nine_colors() -> list[tuple[int, int, int]]:
    return [
        (226, 32, 44),
        (30, 198, 82),
        (36, 78, 224),
        (235, 180, 40),
        (165, 78, 224),
        (32, 178, 190),
        (242, 92, 148),
        (70, 150, 68),
        (55, 55, 62),
    ]


def _pattern_frame(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), color)
    draw = ImageDraw.Draw(image)
    inverse = tuple(255 - channel for channel in color)
    draw.rectangle((70, 70, 1210, 650), outline=inverse, width=16)
    for offset in range(0, 360, 60):
        draw.line((90 + offset, 90, 260 + offset, 260), fill=inverse, width=8)
        draw.line((1020 - offset, 620, 1180 - offset, 460), fill=(255, 255, 255), width=6)
    draw.ellipse((140, 390, 380, 630), outline=(20, 20, 20), width=12)
    draw.rectangle((890, 100, 1170, 260), outline=(240, 240, 240), width=10)
    image.save(path, "JPEG", quality=95)
    return path


def _near_color(
    observed: tuple[int, int, int],
    expected: tuple[int, int, int],
    *,
    tolerance: int = 24,
) -> bool:
    return all(abs(channel - target) <= tolerance for channel, target in zip(observed, expected))
