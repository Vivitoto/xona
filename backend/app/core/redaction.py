from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTED = "********"

_SECRET_KEY_FRAGMENTS = (
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
)
_SECRET_KEY_NAMES = {
    "accesstoken",
    "apikey",
    "appsecret",
    "authorization",
    "bearer",
    "cookie",
    "embyapikey",
    "proxypassword",
    "refreshtoken",
    "secret",
    "setcookie",
    "token",
}

_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[^\s,;]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token|token)=([^&;\s]+)"
)


def redact_payload(payload: Any) -> Any:
    """Return a copy of payload with known secret material replaced."""
    return _redact_value(payload)


def _redact_value(value: Any, field_name: str | None = None) -> Any:
    if field_name is not None and _is_secret_field_name(field_name):
        return None if value is None else REDACTED

    if isinstance(value, str):
        return _redact_string(value)

    if isinstance(value, Mapping):
        return {
            key: _redact_value(item, str(key))
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_redact_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)

    if isinstance(value, set):
        return {_redact_value(item) for item in value}

    return value


def _redact_string(value: str) -> str:
    redacted = _URL_RE.sub(lambda match: _redact_url(match.group(0)), value)
    redacted = _BEARER_RE.sub(r"\1" + REDACTED, redacted)
    return _SECRET_ASSIGNMENT_RE.sub(r"\1=" + REDACTED, redacted)


def _redact_url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value

    netloc = parts.netloc
    if "@" in netloc:
        _, host = netloc.rsplit("@", 1)
        netloc = f"{REDACTED}@{host}"

    query = _redact_query(parts.query)
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _redact_query(query: str) -> str:
    if not query:
        return query

    redacted_parts: list[str] = []
    for part in query.split("&"):
        key, separator, value = part.partition("=")
        if separator and _is_secret_field_name(key):
            redacted_parts.append(f"{key}={REDACTED}")
        else:
            redacted_parts.append(f"{key}{separator}{value}")

    return "&".join(redacted_parts)


def _is_secret_field_name(field_name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", field_name.lower())
    if normalized in _SECRET_KEY_NAMES:
        return True
    if normalized.endswith("token"):
        return True
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)
