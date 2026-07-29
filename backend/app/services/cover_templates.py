from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw, ImageFont, ImageOps

from backend.app.schemas.local_metadata import (
    CoverTemplateName,
    PosterFontId,
    PosterTextEffect,
)


POSTER_SIZE = (1000, 1500)
FANART_SIZE = (1920, 1080)
ASSET_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FALLBACK_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
DEFAULT_TITLE_FONT_BY_TEMPLATE: dict[CoverTemplateName, PosterFontId] = {
    "simple_poster": "source_han_sans",
    "jav_classic_left_strip": "dela_gothic_one",
    "tangxin_vlog": "smiley_sans",
}
MIN_TITLE_ANGLE_DEGREES = -20.0
MAX_TITLE_ANGLE_DEGREES = 20.0
MIN_TITLE_POSITION_PERCENT = 0.0
MAX_TITLE_POSITION_PERCENT = 100.0


class CoverTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedCoverSet:
    poster_path: Path
    fanart_path: Path
    title_font_id: PosterFontId


@dataclass(frozen=True)
class PosterFont:
    id: PosterFontId
    display_name: str
    candidate_paths: tuple[str, ...]


@dataclass(frozen=True)
class TemplateTitleStyle:
    max_font_size: int
    min_font_size: int
    fill: tuple[int, int, int, int]
    stroke_width: int
    stroke_fill: tuple[int, int, int, int]
    effect: PosterTextEffect
    shadow: tuple[int, int]


POSTER_FONTS: dict[PosterFontId, PosterFont] = {
    "source_han_sans": PosterFont(
        id="source_han_sans",
        display_name="Source Han Sans / 思源黑体",
        candidate_paths=(
            str(ASSET_FONT_DIR / "SourceHanSansSC-Bold.otf"),
            str(ASSET_FONT_DIR / "SourceHanSansCN-Bold.otf"),
            str(ASSET_FONT_DIR / "NotoSansCJK-Bold.ttc"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
    ),
    "noto_sans_jp": PosterFont(
        id="noto_sans_jp",
        display_name="Noto Sans JP",
        candidate_paths=(
            str(ASSET_FONT_DIR / "NotoSansJP-Black.ttf"),
            str(ASSET_FONT_DIR / "NotoSansJP-Bold.ttf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
    ),
    "dela_gothic_one": PosterFont(
        id="dela_gothic_one",
        display_name="Dela Gothic One",
        candidate_paths=(
            str(ASSET_FONT_DIR / "DelaGothicOne-Regular.ttf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
    ),
    "bebas_neue": PosterFont(
        id="bebas_neue",
        display_name="Bebas Neue",
        candidate_paths=(
            str(ASSET_FONT_DIR / "BebasNeue-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        ),
    ),
    "anton": PosterFont(
        id="anton",
        display_name="Anton",
        candidate_paths=(
            str(ASSET_FONT_DIR / "Anton-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        ),
    ),
    "smiley_sans": PosterFont(
        id="smiley_sans",
        display_name="Smiley Sans / 得意黑",
        candidate_paths=(
            str(ASSET_FONT_DIR / "SmileySans-Oblique.ttf"),
            str(ASSET_FONT_DIR / "SmileySans-Oblique.otf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
    ),
    "zcool_qingke_huangyou": PosterFont(
        id="zcool_qingke_huangyou",
        display_name="ZCOOL QingKe HuangYou / 站酷庆科黄油体",
        candidate_paths=(
            str(ASSET_FONT_DIR / "ZCOOLQingKeHuangYou-Regular.ttf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
    ),
    "lxgw_wenkai": PosterFont(
        id="lxgw_wenkai",
        display_name="LXGW WenKai / 霞鹜文楷",
        candidate_paths=(
            str(ASSET_FONT_DIR / "LXGWWenKai-Regular.ttf"),
            str(ASSET_FONT_DIR / "LXGWWenKaiScreen-Regular.ttf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ),
    ),
}

DEFAULT_TITLE_STYLE_BY_TEMPLATE: dict[CoverTemplateName, TemplateTitleStyle] = {
    "simple_poster": TemplateTitleStyle(
        max_font_size=74,
        min_font_size=34,
        fill=(255, 255, 255, 255),
        stroke_width=4,
        stroke_fill=(12, 17, 20, 235),
        effect="shadow",
        shadow=(4, 5),
    ),
    "jav_classic_left_strip": TemplateTitleStyle(
        max_font_size=62,
        min_font_size=28,
        fill=(18, 27, 34, 255),
        stroke_width=1,
        stroke_fill=(255, 255, 255, 210),
        effect="shadow",
        shadow=(2, 2),
    ),
    "tangxin_vlog": TemplateTitleStyle(
        max_font_size=86,
        min_font_size=34,
        fill=(255, 255, 255, 255),
        stroke_width=6,
        stroke_fill=(14, 21, 24, 245),
        effect="glow",
        shadow=(0, 0),
    ),
}


def generate_cover_previews(
    *,
    title: str,
    title_angle_degrees: float = 0.0,
    title_position_x_percent: float | None = None,
    title_position_y_percent: float | None = None,
    template: CoverTemplateName,
    title_font_id: PosterFontId | None = None,
    title_font_size: int | None = None,
    title_fill_color: str | None = None,
    title_stroke_color: str | None = None,
    title_stroke_width: int | None = None,
    title_effect: PosterTextEffect | None = None,
    frame_paths: list[Path],
    output_dir: Path,
) -> GeneratedCoverSet:
    if not frame_paths:
        raise CoverTemplateError("at_least_one_frame_required")

    frame_paths = _distinct_frame_paths(frame_paths)
    frames = [_open_frame(path) for path in frame_paths]
    title_angle_degrees = _bounded_title_angle(title_angle_degrees)
    title_position_x_percent = _bounded_title_position(title_position_x_percent)
    title_position_y_percent = _bounded_title_position(title_position_y_percent)
    resolved_title_font_id = _resolve_title_font_id(template, title_font_id)
    title_style = _resolve_title_style(
        template=template,
        title_font_size=title_font_size,
        title_fill_color=title_fill_color,
        title_stroke_color=title_stroke_color,
        title_stroke_width=title_stroke_width,
        title_effect=title_effect,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    poster_key = _cover_key(
        title=title,
        title_angle_degrees=title_angle_degrees,
        title_position_x_percent=title_position_x_percent,
        title_position_y_percent=title_position_y_percent,
        template=template,
        title_font_id=resolved_title_font_id,
        title_style=title_style,
        frame_paths=frame_paths,
    )
    fanart_key = _frame_key(frame_paths=frame_paths[:9])
    poster_path = output_dir / f"poster-{template}-{resolved_title_font_id}-{poster_key}.jpg"
    fanart_path = output_dir / f"fanart-{fanart_key}.jpg"

    poster = _render_poster(
        title=title,
        title_angle_degrees=title_angle_degrees,
        title_position_x_percent=title_position_x_percent,
        title_position_y_percent=title_position_y_percent,
        template=template,
        title_font_id=resolved_title_font_id,
        title_style=title_style,
        frames=frames,
    )
    fanart = _render_fanart(frames[:9])
    poster.save(poster_path, "JPEG", quality=92, optimize=True)
    fanart.save(fanart_path, "JPEG", quality=90, optimize=True)
    return GeneratedCoverSet(
        poster_path=poster_path,
        fanart_path=fanart_path,
        title_font_id=resolved_title_font_id,
    )


def _open_frame(path: Path) -> Image.Image:
    if not path.is_file():
        raise CoverTemplateError(f"frame_not_found:{path}")
    try:
        return Image.open(path).convert("RGB")
    except OSError as exc:
        raise CoverTemplateError(f"frame_unreadable:{path}") from exc


def _distinct_frame_paths(frame_paths: list[Path]) -> list[Path]:
    distinct: list[Path] = []
    seen: set[str] = set()
    for path in frame_paths:
        key = path.resolve().as_posix()
        if key in seen:
            continue
        distinct.append(path)
        seen.add(key)
    return distinct


def _render_poster(
    *,
    title: str,
    title_angle_degrees: float,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
    template: CoverTemplateName,
    title_font_id: PosterFontId,
    title_style: TemplateTitleStyle,
    frames: list[Image.Image],
) -> Image.Image:
    if template == "jav_classic_left_strip":
        return _jav_classic_left_strip(
            title,
            frames,
            title_angle_degrees,
            title_position_x_percent,
            title_position_y_percent,
            title_font_id,
            title_style,
        )
    if template == "tangxin_vlog":
        return _tangxin_vlog(
            title,
            frames[0],
            title_angle_degrees,
            title_position_x_percent,
            title_position_y_percent,
            title_font_id,
            title_style,
        )
    return _simple_poster(
        title,
        frames[0],
        title_angle_degrees,
        title_position_x_percent,
        title_position_y_percent,
        title_font_id,
        title_style,
    )


def _simple_poster(
    title: str,
    frame: Image.Image,
    title_angle_degrees: float,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
    title_font_id: PosterFontId,
    title_style: TemplateTitleStyle,
) -> Image.Image:
    canvas = _cover(frame, POSTER_SIZE)
    overlay = Image.new("RGBA", POSTER_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    band_top = int(POSTER_SIZE[1] * 0.72)
    for y in range(band_top, POSTER_SIZE[1]):
        alpha = int(110 + 95 * ((y - band_top) / max(1, POSTER_SIZE[1] - band_top)))
        draw.line([(0, y), (POSTER_SIZE[0], y)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    canvas = _draw_title_block(
        canvas,
        title,
        box=_positioned_title_box(
            _simple_title_box(),
            title_position_x_percent=title_position_x_percent,
            title_position_y_percent=title_position_y_percent,
        ),
        max_lines=3,
        max_font_size=title_style.max_font_size,
        min_font_size=title_style.min_font_size,
        fill=title_style.fill,
        stroke_width=title_style.stroke_width,
        stroke_fill=title_style.stroke_fill,
        shadow=title_style.shadow if title_style.effect == "shadow" else (0, 0),
        glow=title_style.effect == "glow",
        title_font_id=title_font_id,
        title_angle_degrees=title_angle_degrees,
    )
    return canvas.convert("RGB")


def _jav_classic_left_strip(
    title: str,
    frames: list[Image.Image],
    title_angle_degrees: float,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
    title_font_id: PosterFontId,
    title_style: TemplateTitleStyle,
) -> Image.Image:
    canvas = Image.new("RGB", POSTER_SIZE, (247, 249, 250))
    draw = ImageDraw.Draw(canvas)
    strip_width = 280
    gutter = 22
    title_band_height = 245
    main_box = (
        strip_width + gutter,
        gutter,
        POSTER_SIZE[0] - gutter,
        POSTER_SIZE[1] - title_band_height - gutter,
    )
    strip_box_width = strip_width - gutter * 2
    strip_box_height = (POSTER_SIZE[1] - title_band_height - gutter * 4) // 3

    draw.rectangle((0, 0, strip_width, POSTER_SIZE[1]), fill=(18, 27, 34))
    draw.rectangle(
        (0, POSTER_SIZE[1] - title_band_height, POSTER_SIZE[0], POSTER_SIZE[1]),
        fill=(236, 239, 241),
    )
    for index in range(3):
        source = frames[index % len(frames)]
        top = gutter + index * (strip_box_height + gutter)
        thumb = _cover(source, (strip_box_width, strip_box_height))
        canvas.paste(thumb, (gutter, top))
        draw.rectangle(
            (gutter, top, gutter + strip_box_width, top + strip_box_height),
            outline=(255, 255, 255),
            width=4,
        )

    main = _cover(frames[0], (main_box[2] - main_box[0], main_box[3] - main_box[1]))
    canvas.paste(main, (main_box[0], main_box[1]))
    draw.rectangle(main_box, outline=(18, 27, 34), width=5)
    canvas = _draw_title_block(
        canvas,
        title,
        box=_positioned_title_box(
            _jav_classic_title_box(),
            title_position_x_percent=title_position_x_percent,
            title_position_y_percent=title_position_y_percent,
        ),
        max_lines=3,
        max_font_size=title_style.max_font_size,
        min_font_size=title_style.min_font_size,
        fill=title_style.fill,
        stroke_width=title_style.stroke_width,
        stroke_fill=title_style.stroke_fill,
        shadow=title_style.shadow if title_style.effect == "shadow" else (0, 0),
        glow=title_style.effect == "glow",
        title_font_id=title_font_id,
        title_angle_degrees=title_angle_degrees,
    )
    return canvas.convert("RGB")


def _tangxin_vlog(
    title: str,
    frame: Image.Image,
    title_angle_degrees: float,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
    title_font_id: PosterFontId,
    title_style: TemplateTitleStyle,
) -> Image.Image:
    canvas = _cover(frame, POSTER_SIZE).convert("RGBA")
    overlay = Image.new("RGBA", POSTER_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(POSTER_SIZE[1]):
        distance = abs((y / POSTER_SIZE[1]) - 0.58)
        alpha = int(max(0, min(155, 190 * distance)))
        draw.line([(0, y), (POSTER_SIZE[0], y)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas, overlay)
    canvas = _draw_title_block(
        canvas,
        title,
        box=_positioned_title_box(
            _tangxin_title_box(),
            title_position_x_percent=title_position_x_percent,
            title_position_y_percent=title_position_y_percent,
        ),
        max_lines=3,
        max_font_size=title_style.max_font_size,
        min_font_size=title_style.min_font_size,
        fill=title_style.fill,
        stroke_width=title_style.stroke_width,
        stroke_fill=title_style.stroke_fill,
        shadow=title_style.shadow if title_style.effect == "shadow" else (0, 0),
        glow=title_style.effect == "glow",
        title_font_id=title_font_id,
        title_angle_degrees=title_angle_degrees,
    )
    return canvas.convert("RGB")


def _render_fanart(frames: list[Image.Image]) -> Image.Image:
    if not frames:
        raise CoverTemplateError("at_least_one_frame_required")

    canvas = Image.new("RGB", FANART_SIZE, (0, 0, 0))
    frames = frames[:9]
    columns, rows = _fanart_grid_dimensions(len(frames))
    tile_size = (FANART_SIZE[0] // columns, FANART_SIZE[1] // rows)
    for index, frame in enumerate(frames):
        tile = _cover(frame, tile_size)
        x = (index % columns) * tile_size[0]
        y = (index // columns) * tile_size[1]
        canvas.paste(tile, (x, y))
    return canvas


def _fanart_grid_dimensions(frame_count: int) -> tuple[int, int]:
    if frame_count >= 9:
        return 3, 3
    if frame_count >= 7:
        return 3, 3
    if frame_count >= 5:
        return 3, 2
    if frame_count >= 3:
        return 2, 2
    if frame_count == 2:
        return 2, 1
    return 1, 1


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _simple_title_box() -> tuple[int, int, int, int]:
    band_top = int(POSTER_SIZE[1] * 0.72)
    return (80, band_top + 54, POSTER_SIZE[0] - 80, POSTER_SIZE[1] - 80)


def _jav_classic_title_box() -> tuple[int, int, int, int]:
    strip_width = 280
    gutter = 22
    title_band_height = 245
    return (
        strip_width + gutter,
        POSTER_SIZE[1] - title_band_height + 36,
        POSTER_SIZE[0] - 42,
        POSTER_SIZE[1] - 42,
    )


def _tangxin_title_box() -> tuple[int, int, int, int]:
    return (72, int(POSTER_SIZE[1] * 0.58), POSTER_SIZE[0] - 72, POSTER_SIZE[1] - 95)


def _default_title_box(template: CoverTemplateName) -> tuple[int, int, int, int]:
    if template == "jav_classic_left_strip":
        return _jav_classic_title_box()
    if template == "tangxin_vlog":
        return _tangxin_title_box()
    return _simple_title_box()


def _positioned_title_box(
    default_box: tuple[int, int, int, int],
    *,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = default_box
    width = right - left
    height = bottom - top
    if title_position_x_percent is None:
        positioned_left = left
    else:
        max_left = max(0, POSTER_SIZE[0] - width)
        positioned_left = round(max_left * title_position_x_percent / 100.0)
    if title_position_y_percent is None:
        positioned_top = top
    else:
        max_top = max(0, POSTER_SIZE[1] - height)
        positioned_top = round(max_top * title_position_y_percent / 100.0)
    return (
        int(positioned_left),
        int(positioned_top),
        int(positioned_left + width),
        int(positioned_top + height),
    )


def _draw_title_block(
    image: Image.Image,
    title: str,
    *,
    title_angle_degrees: float,
    box: tuple[int, int, int, int],
    max_lines: int,
    max_font_size: int,
    min_font_size: int,
    fill: tuple[int, int, int, int],
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
    shadow: tuple[int, int],
    title_font_id: PosterFontId,
    glow: bool = False,
) -> Image.Image:
    if abs(title_angle_degrees) < 0.01:
        _draw_title_text(
            ImageDraw.Draw(image),
            title,
            box=box,
            max_lines=max_lines,
            max_font_size=max_font_size,
            min_font_size=min_font_size,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
            shadow=shadow,
            title_font_id=title_font_id,
            glow=glow,
        )
        return image

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    _draw_title_text(
        ImageDraw.Draw(layer),
        title,
        box=box,
        max_lines=max_lines,
        max_font_size=max_font_size,
        min_font_size=min_font_size,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
        shadow=shadow,
        title_font_id=title_font_id,
        glow=glow,
    )
    left, top, right, bottom = box
    rotated = layer.rotate(
        title_angle_degrees,
        resample=Image.Resampling.BICUBIC,
        center=((left + right) / 2, (top + bottom) / 2),
    )
    return Image.alpha_composite(image.convert("RGBA"), rotated)


def _draw_title_text(
    draw: ImageDraw.ImageDraw,
    title: str,
    *,
    box: tuple[int, int, int, int],
    max_lines: int,
    max_font_size: int,
    min_font_size: int,
    fill: tuple[int, int, int, int],
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
    shadow: tuple[int, int],
    title_font_id: PosterFontId,
    glow: bool = False,
) -> None:
    left, top, right, bottom = box
    max_width = max(1, right - left)
    max_height = max(1, bottom - top)

    lines: list[str] = _title_source_lines(title)
    font = _font(min_font_size, title_font_id=title_font_id)
    for size in range(max_font_size, min_font_size - 1, -2):
        candidate_font = _font(size, title_font_id=title_font_id)
        candidate_lines = _wrap_text(title, candidate_font, max_width, max_lines)
        text = "\n".join(candidate_lines)
        width, height = _text_size(draw, text, candidate_font, spacing=max(8, size // 5), stroke_width=stroke_width)
        if width <= max_width and height <= max_height:
            lines = candidate_lines
            font = candidate_font
            break

    text = "\n".join(lines)
    spacing = max(8, getattr(font, "size", min_font_size) // 5)
    width, height = _text_size(draw, text, font, spacing=spacing, stroke_width=stroke_width)
    x = left + (max_width - width) / 2
    y = top + (max_height - height) / 2

    if glow:
        for offset, alpha in ((7, 62), (13, 34)):
            for dx, dy in ((-offset, 0), (offset, 0), (0, -offset), (0, offset)):
                draw.multiline_text(
                    (x + dx, y + dy),
                    text,
                    align="center",
                    fill=(255, 255, 255, alpha),
                    font=font,
                    spacing=spacing,
                    stroke_fill=(255, 255, 255, alpha),
                    stroke_width=stroke_width + 2,
                )
        draw.multiline_text(
            (x + 5, y + 6),
            text,
            align="center",
            fill=(0, 0, 0, 120),
            font=font,
            spacing=spacing,
            stroke_fill=(0, 0, 0, 110),
            stroke_width=stroke_width,
        )

    if shadow != (0, 0):
        draw.multiline_text(
            (x + shadow[0], y + shadow[1]),
            text,
            align="center",
            fill=(0, 0, 0, 150),
            font=font,
            spacing=spacing,
            stroke_fill=(0, 0, 0, 110),
            stroke_width=stroke_width,
        )
    draw.multiline_text(
        (x, y),
        text,
        align="center",
        fill=fill,
        font=font,
        spacing=spacing,
        stroke_fill=stroke_fill,
        stroke_width=stroke_width,
    )


def _wrap_text(
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    source_lines = _title_source_lines(text)
    lines: list[str] = []
    truncated = False
    for index, source_line in enumerate(source_lines):
        remaining = max_lines - len(lines)
        if remaining <= 0:
            truncated = True
            break
        wrapped, consumed = _wrap_single_line(source_line, font, max_width, remaining)
        lines.extend(wrapped)
        if not consumed:
            truncated = True
            break
        if index < len(source_lines) - 1 and len(lines) >= max_lines:
            truncated = True
            break

    if not lines:
        lines = ["Untitled"]
    if truncated:
        lines[-1] = _ellipsize(lines[-1], font, max_width)
    return lines[:max_lines]


def _wrap_single_line(
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> tuple[list[str], bool]:
    units = text.split()
    separator = " "
    if len(units) <= 1:
        units = list(text)
        separator = ""

    lines: list[str] = []
    current = ""
    for index, unit in enumerate(units):
        candidate = unit if not current else f"{current}{separator}{unit}"
        if _line_width(candidate, font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            if len(lines) == max_lines:
                return lines, False
        current = unit
        if _line_width(current, font) > max_width and not lines:
            lines.append(current)
            current = ""
            if len(lines) == max_lines and index < len(units) - 1:
                return lines, False
    if current:
        if len(lines) >= max_lines:
            return lines, False
        lines.append(current)
    return lines or ["Untitled"], True


def _title_source_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()).strip() for line in normalized.split("\n")]
    return [line for line in lines if line] or ["Untitled"]


def _ellipsize(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    value = text
    while value and _line_width(f"{value}...", font) > max_width:
        value = value[:-1].rstrip()
    return f"{value}..." if value else "..."


def _line_width(text: str, font: ImageFont.ImageFont) -> int:
    left, _top, right, _bottom = font.getbbox(text)
    return right - left


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    *,
    spacing: int,
    stroke_width: int,
) -> tuple[int, int]:
    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=spacing,
        stroke_width=stroke_width,
    )
    return int(right - left), int(bottom - top)


def _font(size: int, *, title_font_id: PosterFontId = "source_han_sans") -> ImageFont.ImageFont:
    for path in _font_candidate_paths(title_font_id):
        font_path = Path(path)
        if not font_path.is_file():
            continue
        try:
            return cast(ImageFont.ImageFont, ImageFont.truetype(str(font_path), size=size))
        except OSError:
            continue
    return cast(ImageFont.ImageFont, ImageFont.load_default())


def _font_candidate_paths(title_font_id: PosterFontId) -> tuple[str, ...]:
    poster_font = POSTER_FONTS.get(title_font_id)
    if poster_font is None:
        raise CoverTemplateError(f"unknown_poster_font:{title_font_id}")
    return (*poster_font.candidate_paths, *FALLBACK_FONT_CANDIDATES)


def _resolve_title_font_id(
    template: CoverTemplateName,
    title_font_id: PosterFontId | None,
) -> PosterFontId:
    resolved = title_font_id or DEFAULT_TITLE_FONT_BY_TEMPLATE[template]
    if resolved not in POSTER_FONTS:
        raise CoverTemplateError(f"unknown_poster_font:{resolved}")
    return resolved


def _resolve_title_style(
    *,
    template: CoverTemplateName,
    title_font_size: int | None,
    title_fill_color: str | None,
    title_stroke_color: str | None,
    title_stroke_width: int | None,
    title_effect: PosterTextEffect | None,
) -> TemplateTitleStyle:
    defaults = DEFAULT_TITLE_STYLE_BY_TEMPLATE[template]
    max_font_size = defaults.max_font_size if title_font_size is None else title_font_size
    stroke_width = defaults.stroke_width if title_stroke_width is None else title_stroke_width
    effect = title_effect or defaults.effect
    return TemplateTitleStyle(
        max_font_size=max_font_size,
        min_font_size=min(defaults.min_font_size, max_font_size),
        fill=_hex_to_rgba(title_fill_color, defaults.fill),
        stroke_width=stroke_width,
        stroke_fill=_hex_to_rgba(title_stroke_color, defaults.stroke_fill),
        effect=effect,
        shadow=defaults.shadow,
    )


def _hex_to_rgba(
    value: str | None,
    default: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    if value is None:
        return default
    normalized = value.strip()
    if len(normalized) != 7 or not normalized.startswith("#"):
        raise CoverTemplateError(f"invalid_title_color:{value}")
    try:
        red = int(normalized[1:3], 16)
        green = int(normalized[3:5], 16)
        blue = int(normalized[5:7], 16)
    except ValueError as exc:
        raise CoverTemplateError(f"invalid_title_color:{value}") from exc
    return red, green, blue, default[3]


def _cover_key(
    *,
    title: str,
    title_angle_degrees: float,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
    template: CoverTemplateName,
    title_font_id: PosterFontId,
    title_style: TemplateTitleStyle,
    frame_paths: list[Path],
) -> str:
    normalized_x_percent, normalized_y_percent = _title_position_key_values(
        template=template,
        title_position_x_percent=title_position_x_percent,
        title_position_y_percent=title_position_y_percent,
    )
    digest = hashlib.sha256()
    digest.update(title.encode("utf-8"))
    digest.update(f"{_bounded_title_angle(title_angle_degrees):.4f}".encode("ascii"))
    digest.update(f"{normalized_x_percent:.4f}".encode("ascii"))
    digest.update(f"{normalized_y_percent:.4f}".encode("ascii"))
    digest.update(template.encode("utf-8"))
    digest.update(title_font_id.encode("utf-8"))
    digest.update(str(title_style.max_font_size).encode("ascii"))
    digest.update(",".join(str(channel) for channel in title_style.fill).encode("ascii"))
    digest.update(str(title_style.stroke_width).encode("ascii"))
    digest.update(",".join(str(channel) for channel in title_style.stroke_fill).encode("ascii"))
    digest.update(title_style.effect.encode("ascii"))
    _update_frame_digest(digest, frame_paths)
    return digest.hexdigest()[:16]


def _frame_key(*, frame_paths: list[Path]) -> str:
    digest = hashlib.sha256()
    _update_frame_digest(digest, frame_paths)
    return digest.hexdigest()[:16]


def _update_frame_digest(digest: Any, frame_paths: list[Path]) -> None:
    for path in frame_paths:
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            stat = path.stat()
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))


def _bounded_title_angle(value: float) -> float:
    return min(MAX_TITLE_ANGLE_DEGREES, max(MIN_TITLE_ANGLE_DEGREES, float(value)))


def _bounded_title_position(value: float | None) -> float | None:
    if value is None:
        return None
    return min(MAX_TITLE_POSITION_PERCENT, max(MIN_TITLE_POSITION_PERCENT, float(value)))


def _title_position_key_values(
    *,
    template: CoverTemplateName,
    title_position_x_percent: float | None,
    title_position_y_percent: float | None,
) -> tuple[float, float]:
    default_box = _default_title_box(template)
    return (
        _default_title_position_percent(default_box, axis="x")
        if title_position_x_percent is None
        else title_position_x_percent,
        _default_title_position_percent(default_box, axis="y")
        if title_position_y_percent is None
        else title_position_y_percent,
    )


def _default_title_position_percent(
    box: tuple[int, int, int, int],
    *,
    axis: str,
) -> float:
    left, top, right, bottom = box
    if axis == "x":
        travel = POSTER_SIZE[0] - (right - left)
        return 0.0 if travel <= 0 else (left / travel) * 100.0
    travel = POSTER_SIZE[1] - (bottom - top)
    return 0.0 if travel <= 0 else (top / travel) * 100.0
