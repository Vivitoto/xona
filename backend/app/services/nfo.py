from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from backend.app.schemas.metadata import MetadataRecordData


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
    unique_id = ElementTree.SubElement(
        movie,
        "uniqueid",
        {"type": record.source, "default": "true"},
    )
    unique_id.text = record.xchina_id
    _sub(movie, "id", record.xchina_id)
    _sub(movie, "sourceurl", record.source_url)
    ElementTree.indent(movie)
    return ElementTree.tostring(movie, encoding="utf-8", xml_declaration=True)


def _sub(parent: ElementTree.Element, name: str, value: str | None) -> None:
    if value is None or value == "":
        return
    child = ElementTree.SubElement(parent, name)
    child.text = value
