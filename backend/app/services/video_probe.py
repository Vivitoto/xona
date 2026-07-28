from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.app.schemas.local_metadata import LocalVideoTechnicalInfo


class MediaToolUnavailableError(ValueError):
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"{tool_name} is not available")
        self.tool_name = tool_name


class MediaToolExecutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def probe_video(video_path: Path | str) -> LocalVideoTechnicalInfo:
    path = Path(video_path)
    if shutil.which("ffprobe") is None:
        raise MediaToolUnavailableError("ffprobe")
    if not path.is_file():
        raise MediaToolExecutionError("video_not_found", f"Video file does not exist: {path}")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaToolExecutionError("ffprobe_timeout", "ffprobe timed out") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or "ffprobe failed"
        raise MediaToolExecutionError("ffprobe_failed", message)

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaToolExecutionError("ffprobe_invalid_json", "ffprobe returned invalid JSON") from exc

    return _technical_info(path, payload)


def extract_video_frames(
    video_path: Path | str,
    *,
    output_dir: Path | str,
    times_seconds: list[float],
) -> list[tuple[Path, float]]:
    if shutil.which("ffmpeg") is None:
        raise MediaToolUnavailableError("ffmpeg")

    path = Path(video_path)
    if not path.is_file():
        raise MediaToolExecutionError("video_not_found", f"Video file does not exist: {path}")

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    generated: list[tuple[Path, float]] = []
    for index, time_seconds in enumerate(times_seconds, start=1):
        safe_time = max(0.0, float(time_seconds))
        output_path = directory / f"frame-{index:02d}.jpg"
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{safe_time:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(output_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaToolExecutionError("ffmpeg_timeout", "ffmpeg timed out") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or "ffmpeg failed"
            raise MediaToolExecutionError("ffmpeg_failed", message)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise MediaToolExecutionError("ffmpeg_no_frame", "ffmpeg did not produce a frame")
        generated.append((output_path, safe_time))
    return generated


def _technical_info(path: Path, payload: dict[str, Any]) -> LocalVideoTechnicalInfo:
    streams = payload.get("streams")
    if not isinstance(streams, list):
        streams = []
    video_stream = _first_stream(streams, "video")
    audio_stream = _first_stream(streams, "audio")
    raw_format = payload.get("format")
    media_format: dict[str, Any] = raw_format if isinstance(raw_format, dict) else {}
    duration = _float_value(media_format.get("duration"))
    if duration is None and video_stream is not None:
        duration = _float_value(video_stream.get("duration"))

    return LocalVideoTechnicalInfo(
        path=path,
        size_bytes=path.stat().st_size,
        duration_seconds=duration,
        width=_int_value(video_stream.get("width") if video_stream else None),
        height=_int_value(video_stream.get("height") if video_stream else None),
        video_codec=_text_value(video_stream.get("codec_name") if video_stream else None),
        audio_codec=_text_value(audio_stream.get("codec_name") if audio_stream else None),
        format_name=_text_value(media_format.get("format_name")),
        bit_rate=_int_value(media_format.get("bit_rate")),
        fps=_fps_value(video_stream.get("avg_frame_rate") if video_stream else None),
    )


def _first_stream(streams: list[Any], codec_type: str) -> dict[str, Any] | None:
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
            return stream
    return None


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fps_value(value: Any) -> float | None:
    text = _text_value(value)
    if not text or text in {"0/0", "N/A"}:
        return None
    if "/" not in text:
        return _float_value(text)
    numerator, denominator = text.split("/", 1)
    numerator_value = _float_value(numerator)
    denominator_value = _float_value(denominator)
    if numerator_value is None or not denominator_value:
        return None
    return numerator_value / denominator_value
