from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class FetchedAsset:
    url: str
    content: bytes
    content_type: str


GENERIC_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "text/plain",
}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


def normalize_fetched_asset(asset: FetchedAsset, *, fallback_url: str | None = None) -> FetchedAsset:
    return FetchedAsset(
        url=asset.url or fallback_url or "",
        content=asset.content,
        content_type=detect_content_type(
            asset.content,
            declared_content_type=asset.content_type,
            url=asset.url or fallback_url,
        ),
    )


def detect_content_type(
    content: bytes,
    *,
    declared_content_type: str | None = None,
    url: str | None = None,
) -> str:
    declared = normalize_content_type(declared_content_type)
    if declared in HTML_CONTENT_TYPES:
        return declared
    if sniff_html(content):
        return "text/html"

    sniffed = sniff_image_content_type(content)
    if declared in GENERIC_CONTENT_TYPES:
        if sniffed:
            return sniffed
        guessed = guess_content_type_from_url(url or "")
        return guessed if guessed != "application/octet-stream" else (declared or guessed)

    if declared:
        return declared
    if sniffed:
        return sniffed
    return guess_content_type_from_url(url or "")


def normalize_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return str(content_type).split(";", 1)[0].strip().lower()


def content_type_from_headers(headers: Mapping[str, Any] | None) -> str | None:
    if not headers:
        return None
    for key, value in headers.items():
        if str(key).lower() != "content-type":
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        normalized = normalize_content_type(str(value) if value is not None else None)
        return normalized or None
    return None


def guess_content_type_from_url(url: str) -> str:
    parsed = urlsplit(url)
    guessed, _encoding = mimetypes.guess_type(parsed.path or url)
    return normalize_content_type(guessed) or "application/octet-stream"


def sniff_image_content_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"BM"):
        return "image/bmp"

    leading = _leading_text(content[:1024])
    if leading.startswith("<svg") or (leading.startswith("<?xml") and "<svg" in leading[:512]):
        return "image/svg+xml"
    return None


def sniff_html(content: bytes) -> bool:
    leading = _leading_text(content[:512])
    if leading.startswith("<?xml") and "<html" in leading[:512]:
        return True
    return leading.startswith(
        (
            "<!doctype html",
            "<html",
            "<head",
            "<body",
            "<script",
            "<title",
        )
    )


def _leading_text(content: bytes) -> str:
    return content.lstrip(b"\xef\xbb\xbf\x00\t\n\r ").decode(
        "utf-8",
        errors="ignore",
    ).lstrip().lower()
