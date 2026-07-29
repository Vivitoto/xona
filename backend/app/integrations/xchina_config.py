from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

DEFAULT_XCHINA_BASE_URL = "https://xchina.co"
DEFAULT_XCHINA_MAX_SEARCH_PAGES = 50
DEFAULT_XCHINA_IMAGE_HOSTS = {
    "en.xchina.co",
    "www.xchina.co",
    "xchina.co",
    "img.xchina.download",
    "upload.xchina.io",
}
DEFAULT_XCHINA_SITE_HOSTS = {
    "en.xchina.co",
    "www.xchina.co",
    "xchina.co",
}


def xchina_base_url(store_settings: Mapping[str, Any] | None) -> str:
    configured = (store_settings or {}).get("base_url")
    if isinstance(configured, str) and configured.strip():
        return normalize_xchina_base_url(configured)
    return DEFAULT_XCHINA_BASE_URL


def normalize_xchina_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("XChina base URL must be an absolute http(s) origin")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("XChina base URL must include a valid port") from exc
    if parsed.username or parsed.password:
        raise ValueError("XChina base URL must not include credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("XChina base URL must be an origin without path, query, or fragment")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def xchina_max_search_pages(store_settings: Mapping[str, Any] | None) -> int:
    configured = (store_settings or {}).get("max_search_pages")
    if isinstance(configured, int):
        return max(1, configured)
    if isinstance(configured, str) and configured.strip():
        try:
            return max(1, int(configured.strip()))
        except ValueError:
            return DEFAULT_XCHINA_MAX_SEARCH_PAGES
    return DEFAULT_XCHINA_MAX_SEARCH_PAGES


def xchina_allowed_image_hosts(store_settings: Mapping[str, Any] | None) -> set[str]:
    hosts = set(DEFAULT_XCHINA_IMAGE_HOSTS)
    parsed = urlsplit(xchina_base_url(store_settings))
    if parsed.hostname:
        hosts.add(parsed.hostname.lower())
    return hosts


def is_allowed_xchina_resource_url(
    url: str,
    store_settings: Mapping[str, Any] | None,
) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    return parsed.hostname.lower() in xchina_allowed_image_hosts(store_settings)


def is_allowed_xchina_detail_url(
    url: str,
    store_settings: Mapping[str, Any] | None,
) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password:
        return False
    if not _is_allowed_xchina_detail_path(parsed.path):
        return False

    base = urlsplit(xchina_base_url(store_settings))
    if parsed.scheme.lower() != base.scheme.lower():
        return False
    if _effective_port(parsed) != _effective_port(base):
        return False

    candidate_host = parsed.hostname.lower()
    base_host = (base.hostname or "").lower()
    if candidate_host == base_host:
        return True
    return candidate_host in DEFAULT_XCHINA_SITE_HOSTS and base_host in DEFAULT_XCHINA_SITE_HOSTS


def _is_allowed_xchina_detail_path(path: str) -> bool:
    return path in {"/video", "/videos"} or path.startswith("/video/") or path.startswith("/videos/")


def _effective_port(parts: Any) -> int | None:
    try:
        explicit_port = parts.port
    except ValueError:
        return None
    if explicit_port is not None:
        return explicit_port
    if parts.scheme == "http":
        return 80
    if parts.scheme == "https":
        return 443
    return None
