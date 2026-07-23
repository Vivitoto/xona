from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from backend.app.schemas.normalization import NormalizedName


IDENTIFIER_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{2,10})([-_ ]?)(\d{2,6})(?![A-Z0-9])")
SITE_PREFIX_RE = re.compile(r"^(xchina|site-prefix|release-site)[\s._-]+", re.IGNORECASE)
MULTIPART_RE = re.compile(r"(?:[\s._-]+|^)(?:cd|disc|disk|part)[\s._-]*(\d{1,3})$", re.IGNORECASE)
RELEASE_SUFFIX_RE = re.compile(r"[\s._-]+(release|rip)$", re.IGNORECASE)
TECHNICAL_TOKEN_RE = re.compile(
    r"^(?:\d{3,4}p|4k|8k|web[-_. ]?dl|web[-_. ]?rip|blu[-_. ]?ray|x264|x265|h264|h265|hevc|aac|ddp?|proper|repack)$",
    re.IGNORECASE,
)
BRACKET_RE = re.compile(r"[\[(]([^\])]+)[\])]")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def normalize_filename_for_search(
    filename: str | Path, *, parent_name: str | None = None
) -> NormalizedName:
    original = str(filename)
    value = unicodedata.normalize("NFKC", Path(original).name)
    stem = Path(value).stem

    technical_tokens: list[str] = []
    stem = _strip_bracketed_technical_tokens(stem, technical_tokens)

    site_prefix = None
    site_match = SITE_PREFIX_RE.match(stem)
    if site_match is not None:
        site_prefix = site_match.group(1)
        stem = stem[site_match.end() :]

    multipart_index = None
    multipart_match = MULTIPART_RE.search(stem)
    if multipart_match is not None:
        multipart_index = int(multipart_match.group(1))
        stem = stem[: multipart_match.start()]

    release_suffix = None
    release_match = RELEASE_SUFFIX_RE.search(stem)
    if release_match is not None:
        release_suffix = release_match.group(1)
        stem = stem[: release_match.start()]

    identifier = _extract_identifier(stem)
    protected_identifier = "XONAIDENTIFIERPLACEHOLDER"
    if identifier:
        stem = IDENTIFIER_RE.sub(protected_identifier, stem, count=1)

    tokens: list[str] = []
    for raw_token in re.split(r"[\s._-]+", stem):
        token = raw_token.strip()
        if not token:
            continue
        if token == protected_identifier:
            tokens.append(identifier or token)
            continue
        if TECHNICAL_TOKEN_RE.match(token):
            technical_tokens.append(token)
            continue
        tokens.append(token)

    search_text = " ".join(tokens)
    search_text = re.sub(r"\s+", " ", search_text).strip()
    return NormalizedName(
        original=original,
        search_text=search_text or (identifier or ""),
        identifier=identifier,
        parent_hint=_clean_hint(parent_name),
        site_prefix=site_prefix,
        release_suffix=release_suffix,
        multipart_index=multipart_index,
        technical_tokens=technical_tokens,
    )


def sanitize_path_component(value: str, max_length: int = 180) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = CONTROL_RE.sub("", normalized)
    parts = [
        part.strip(" .")
        for part in re.split(r"[\\/]+", normalized)
        if part.strip(" .") and part.strip(" .") not in {".", ".."}
    ]
    cleaned = "_".join(parts) if parts else normalized.strip(" .")
    cleaned = re.sub(r'[:*?"<>|]+', "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    if not cleaned:
        cleaned = "untitled"
    if cleaned.upper() in WINDOWS_RESERVED:
        cleaned = f"{cleaned}_"
    return cleaned[:max_length] or "untitled"


def _strip_bracketed_technical_tokens(value: str, tokens: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        fragment = match.group(1)
        fragment_tokens = [part for part in fragment.split() if part]
        if fragment_tokens and all(TECHNICAL_TOKEN_RE.match(part) for part in fragment_tokens):
            tokens.extend(fragment_tokens)
            return " "
        return match.group(0)

    return BRACKET_RE.sub(replace, value)


def _extract_identifier(value: str) -> str | None:
    match = IDENTIFIER_RE.search(value.upper())
    if match is None:
        return None
    prefix, separator, number = match.groups()
    return f"{prefix}{'-' if separator == '-' else ''}{number}"


def _clean_hint(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    return cleaned or None
