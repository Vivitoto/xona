from __future__ import annotations
import math
from pathlib import Path
from xml.etree import ElementTree

from backend.app.schemas.metadata import MetadataRecordData, MetadataTechnicalInfo


def movie_nfo_relative_path(template_filename: str) -> str:
    return f"{Path(template_filename).stem}.nfo"


def render_movie_nfo(record: MetadataRecordData) -> bytes:
    movie = ElementTree.Element("movie")
    _sub(movie, "title", record.title)
    _sub(movie, "originaltitle", record.original_title)
    _sub(movie, "sorttitle", record.sort_title or record.title)
    _sub(movie, "plot", record.plot)
    _sub(movie, "outline", record.outline or record.plot)
    _sub(movie, "premiered", record.release_date)
    _sub(movie, "releasedate", record.release_date)
    if record.runtime_minutes is not None:
        _sub(movie, "runtime", str(record.runtime_minutes))
    _sub(movie, "studio", record.studio)
    if record.series:
        set_element = ElementTree.SubElement(movie, "set")
        _sub(set_element, "name", record.series)
    _sub(movie, "director", record.director)
    for actor in record.actors:
        actor_element = ElementTree.SubElement(movie, "actor")
        _sub(actor_element, "name", actor.name)
        _sub(actor_element, "role", actor.role)
        _sub(actor_element, "profile", actor.profile_url)
        _sub(actor_element, "thumb", actor.portrait_reference or actor.portrait_url)
    for genre in record.genres:
        _sub(movie, "genre", genre)
    for tag in record.tags:
        _sub(movie, "tag", tag)
    for label in record.labels:
        _sub(movie, "label", label)
    _append_stream_details(movie, record.technical)
    unique_id = ElementTree.SubElement(
        movie,
        "uniqueid",
        {"type": record.source, "default": "true"},
    )
    unique_id.text = record.source_id
    _sub(movie, "id", record.source_id)
    _sub(movie, "sourceurl", record.source_url)
    ElementTree.indent(movie)
    return ElementTree.tostring(movie, encoding="utf-8", xml_declaration=True)


def _sub(parent: ElementTree.Element, name: str, value: str | None) -> None:
    if value is None or value == "":
        return
    child = ElementTree.SubElement(parent, name)
    child.text = value


def _append_stream_details(
    movie: ElementTree.Element,
    technical: MetadataTechnicalInfo | None,
) -> None:
    if technical is None:
        return
    if not any(
        value is not None
        for value in (
            technical.video_codec,
            technical.width,
            technical.height,
            technical.bit_rate,
            technical.fps,
            technical.duration_seconds,
            technical.audio_codec,
        )
    ):
        return

    fileinfo = ElementTree.SubElement(movie, "fileinfo")
    streamdetails = ElementTree.SubElement(fileinfo, "streamdetails")
    if any(
        value is not None
        for value in (
            technical.video_codec,
            technical.width,
            technical.height,
            technical.bit_rate,
            technical.fps,
            technical.duration_seconds,
        )
    ):
        video = ElementTree.SubElement(streamdetails, "video")
        _sub(video, "codec", technical.video_codec)
        _sub(video, "micodec", technical.video_codec)
        _sub(video, "bitrate", _int_text(technical.bit_rate))
        _sub(video, "width", _int_text(technical.width))
        _sub(video, "height", _int_text(technical.height))
        aspect = _aspect_ratio(technical.width, technical.height)
        _sub(video, "aspect", aspect)
        _sub(video, "aspectratio", aspect)
        _sub(video, "framerate", _float_text(technical.fps))
        _sub(video, "duration", _duration_minutes_text(technical.duration_seconds))
        _sub(video, "durationinseconds", _duration_seconds_text(technical.duration_seconds))

    if technical.audio_codec:
        audio = ElementTree.SubElement(streamdetails, "audio")
        _sub(audio, "codec", technical.audio_codec)
        _sub(audio, "micodec", technical.audio_codec)


def _aspect_ratio(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    divisor = math.gcd(width, height)
    if divisor <= 0:
        return None
    return f"{width // divisor}:{height // divisor}"


def _int_text(value: int | None) -> str | None:
    return str(value) if value is not None else None


def _float_text(value: float | None) -> str | None:
    if value is None:
        return None
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _duration_seconds_text(value: float | None) -> str | None:
    if value is None:
        return None
    return str(max(0, int(round(value))))


def _duration_minutes_text(value: float | None) -> str | None:
    if value is None:
        return None
    return str(max(1, int(round(value / 60))))
