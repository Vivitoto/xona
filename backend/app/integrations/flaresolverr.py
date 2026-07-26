from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx

from backend.app.core.redaction import redact_payload
from backend.app.integrations.assets import (
    FetchedAsset,
    content_type_from_headers,
    detect_content_type,
)


SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)
ASSET_ACCEPT = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
XCHINA_HOST_SUFFIXES = (".xchina.co", ".xchina.io", ".xchina.download")
XCHINA_HOSTS = {"xchina.co", "xchina.io", "xchina.download"}


class FlareSolverrError(RuntimeError):
    pass


class FlareSolverrStatusError(FlareSolverrError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class FlareSolverrAssetError(FlareSolverrError):
    def __init__(
        self,
        message: str,
        *,
        reason: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class FlareSolverrResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
    user_agent: str | None = None
    content: bytes | None = None


@dataclass(frozen=True)
class ParsedProxy:
    url: str
    username: str | None = None
    password: str | None = None

    @property
    def credentialed(self) -> bool:
        return self.username is not None or self.password is not None

    def request_payload(self) -> dict[str, str]:
        return {"url": self.url}

    def session_payload(self) -> dict[str, str]:
        payload = {"url": self.url}
        if self.username is not None:
            payload["username"] = self.username
        if self.password is not None:
            payload["password"] = self.password
        return payload

    def httpx_url(self) -> str:
        if self.username is None and self.password is None:
            return self.url
        parts = urlsplit(self.url)
        credentials = quote(self.username or "", safe="")
        if self.password is not None:
            credentials = f"{credentials}:{quote(self.password, safe='')}"
        netloc = f"{credentials}@{parts.hostname or ''}"
        if parts.port is not None:
            netloc = f"{netloc}:{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class FlareSolverrClient:
    def __init__(
        self,
        endpoint: str,
        *,
        proxy_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        asset_http_client: httpx.AsyncClient | None = None,
        max_timeout_ms: int = 60_000,
    ) -> None:
        self._endpoint = endpoint
        self._proxy = parse_proxy_url(proxy_url) if proxy_url else None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout((max_timeout_ms / 1000) + 10)
        )
        self._asset_http_client = asset_http_client
        self._owns_http_client = http_client is None
        self._owns_asset_http_client = asset_http_client is None
        self._max_timeout_ms = max_timeout_ms
        self._proxy_session_id: str | None = None

    async def close(self) -> None:
        await self._destroy_persistent_proxy_session()
        if self._owns_http_client:
            await self._http_client.aclose()
        if self._owns_asset_http_client and self._asset_http_client is not None:
            await self._asset_http_client.aclose()

    async def __aenter__(self) -> "FlareSolverrClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def request_get(self, url: str, *, session_id: str | None = None) -> FlareSolverrResponse:
        if session_id is not None or self._proxy is None:
            return await self._request_get_once(url, session_id=session_id)

        return await self._request_get_with_persistent_proxy_session(url)

    async def _request_get_with_persistent_proxy_session(self, url: str) -> FlareSolverrResponse:
        for attempt in range(2):
            session_id = await self._persistent_proxy_session()
            try:
                return await self._request_get_once(url, session_id=session_id)
            except FlareSolverrStatusError as exc:
                if exc.status_code not in {403, 503}:
                    raise
                await self._invalidate_proxy_session(session_id)
                if attempt == 1:
                    raise
            except FlareSolverrError:
                await self._invalidate_proxy_session(session_id)
                if attempt == 1:
                    raise
        raise AssertionError("unreachable proxy session retry state")

    async def _request_get_once(
        self, url: str, *, session_id: str | None = None
    ) -> FlareSolverrResponse:
        result = await self._post(self._request_payload(url, session_id=session_id))
        solution = _solution(result)
        try:
            status_code = int(solution.get("status") or 0)
        except (TypeError, ValueError) as exc:
            raise self._error("Malformed FlareSolverr response", result) from exc
        if status_code >= 400:
            reason = "Cloudflare block" if status_code in {403, 503} else "HTTP error"
            raise self._status_error(reason, result, status_code=status_code)
        try:
            text, content = _solution_response_body(solution)
        except ValueError as exc:
            raise self._error("Malformed FlareSolverr response", result) from exc
        if text is None:
            raise self._error("Malformed FlareSolverr response", result)
        return FlareSolverrResponse(
            url=str(solution.get("url") or url),
            status_code=status_code,
            text=text,
            headers=_solution_headers(solution),
            cookies=_solution_cookies(solution),
            user_agent=_solution_user_agent(solution),
            content=content,
        )

    async def request_asset(
        self,
        url: str,
        *,
        session_id: str | None = None,
        referer_url: str | None = None,
        base_url: str | None = None,
    ) -> FetchedAsset:
        headers = _asset_request_headers(
            url,
            referer_url=referer_url,
            base_url=base_url,
        )
        try:
            return await self._request_asset_direct(url, headers=headers)
        except FlareSolverrAssetError as direct_error:
            fallback_errors: list[FlareSolverrError] = [direct_error]

        solution: FlareSolverrResponse | None = None
        context_url = _asset_context_url(url, referer_url=referer_url, base_url=base_url)
        if context_url is not None:
            try:
                solution = await self.request_get(context_url, session_id=session_id)
            except FlareSolverrError as exc:
                fallback_errors.append(exc)

        if solution is not None:
            retry_headers = _asset_request_headers(
                url,
                referer_url=referer_url or solution.url,
                base_url=base_url,
                user_agent=solution.user_agent,
            )
            try:
                return await self._request_asset_direct(
                    url,
                    headers=_headers_with_cookies(retry_headers, solution.cookies),
                )
            except FlareSolverrAssetError as exc:
                fallback_errors.append(exc)

        try:
            return await self._request_asset_via_flaresolverr(
                url,
                session_id=session_id,
                saw_forbidden=_saw_status(fallback_errors, 403),
            )
        except FlareSolverrAssetError as exc:
            fallback_errors.append(exc)

        status_code = 403 if _saw_status(fallback_errors, 403) else _last_status_code(fallback_errors)
        reason = "hotlink_forbidden" if status_code == 403 else "download_failed"
        message = "Asset request forbidden" if reason == "hotlink_forbidden" else "Asset request failed"
        raise self._asset_error(
            message,
            {
                "url": url,
                "status_code": status_code,
                "proxy": self._proxy.session_payload() if self._proxy else None,
            },
            reason=reason,
            status_code=status_code,
        )

    async def _request_asset_direct(
        self,
        url: str,
        *,
        headers: dict[str, str],
    ) -> FetchedAsset:
        try:
            response = await self._asset_client().get(
                url,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise self._asset_error(
                "Asset request timeout",
                {"url": url, "proxy": self._proxy.session_payload() if self._proxy else None},
                reason="download_failed",
            ) from exc
        except httpx.HTTPError as exc:
            raise self._asset_error(
                "Asset request failed",
                {"url": url, "proxy": self._proxy.session_payload() if self._proxy else None},
                reason="download_failed",
            ) from exc
        if response.status_code >= 400:
            reason = "hotlink_forbidden" if response.status_code == 403 else "download_failed"
            message = "Asset request forbidden" if reason == "hotlink_forbidden" else "Asset request failed"
            raise self._asset_error(
                message,
                {
                    "url": url,
                    "status_code": response.status_code,
                    "proxy": self._proxy.session_payload() if self._proxy else None,
                },
                reason=reason,
                status_code=response.status_code,
            )
        content = response.content
        final_url = str(response.url or url)
        declared_content_type = content_type_from_headers(response.headers)
        return FetchedAsset(
            url=final_url,
            content=content,
            content_type=detect_content_type(
                content,
                declared_content_type=declared_content_type,
                url=final_url,
            ),
        )

    async def _request_asset_via_flaresolverr(
        self,
        url: str,
        *,
        session_id: str | None,
        saw_forbidden: bool,
    ) -> FetchedAsset:
        try:
            response = await self.request_get(url, session_id=session_id)
        except FlareSolverrStatusError as exc:
            reason = "hotlink_forbidden" if exc.status_code == 403 else "download_failed"
            raise self._asset_error(
                "FlareSolverr asset request forbidden"
                if reason == "hotlink_forbidden"
                else "FlareSolverr asset request failed",
                {"url": url, "status_code": exc.status_code},
                reason=reason,
                status_code=exc.status_code,
            ) from exc
        except FlareSolverrError as exc:
            raise self._asset_error(
                "FlareSolverr asset request failed",
                {"url": url},
                reason="hotlink_forbidden" if saw_forbidden else "download_failed",
                status_code=403 if saw_forbidden else None,
            ) from exc

        content = response.content if response.content is not None else response.text.encode("utf-8")
        final_url = response.url or url
        content_type = detect_content_type(
            content,
            declared_content_type=content_type_from_headers(response.headers),
            url=final_url,
        )
        if _looks_like_binary_asset_url(url) and content_type in HTML_CONTENT_TYPES:
            raise self._asset_error(
                "FlareSolverr asset request returned HTML",
                {"url": url, "solver_status_code": response.status_code},
                reason="hotlink_forbidden" if saw_forbidden else "download_failed",
                status_code=403 if saw_forbidden else None,
            )
        return FetchedAsset(url=final_url, content=content, content_type=content_type)

    def _asset_client(self) -> httpx.AsyncClient:
        if self._asset_http_client is None:
            self._asset_http_client = httpx.AsyncClient(
                timeout=httpx.Timeout((self._max_timeout_ms / 1000) + 10),
                follow_redirects=True,
                proxy=self._proxy.httpx_url() if self._proxy is not None else None,
                headers={
                    "User-Agent": BROWSER_USER_AGENT,
                    "Accept": ASSET_ACCEPT,
                },
            )
            self._owns_asset_http_client = True
        return self._asset_http_client

    async def create_session(self) -> str:
        payload: dict[str, Any] = {"cmd": "sessions.create"}
        if self._proxy is not None:
            payload["proxy"] = self._proxy.session_payload()
        result = await self._post(payload)
        session_id = result.get("session")
        if not isinstance(session_id, str) or not session_id:
            raise self._error("FlareSolverr session creation failed", result)
        return session_id

    async def destroy_session(self, session_id: str) -> None:
        result = await self._post({"cmd": "sessions.destroy", "session": session_id})
        if result.get("status") != "ok":
            raise self._error("FlareSolverr session destroy failed", result)

    async def test_connection(self, url: str = "https://example.test/") -> bool:
        await self.request_get(url)
        return True

    def _request_payload(self, url: str, *, session_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self._max_timeout_ms,
        }
        if session_id is not None:
            payload["session"] = session_id
        return payload

    async def _persistent_proxy_session(self) -> str:
        if self._proxy is None:
            raise FlareSolverrError("Persistent proxy session requested without a proxy")
        if self._proxy_session_id is None:
            self._proxy_session_id = await self.create_session()
        return self._proxy_session_id

    async def _invalidate_proxy_session(self, session_id: str) -> None:
        if self._proxy_session_id != session_id:
            return
        self._proxy_session_id = None
        with suppress(Exception):
            await self.destroy_session(session_id)

    async def _destroy_persistent_proxy_session(self) -> None:
        session_id = self._proxy_session_id
        self._proxy_session_id = None
        if session_id is not None:
            with suppress(Exception):
                await self.destroy_session(session_id)

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http_client.post(self._endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise self._error("FlareSolverr timeout", {"endpoint": self._endpoint, "payload": payload}) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise self._error("FlareSolverr request failed", {"endpoint": self._endpoint, "payload": payload}) from exc
        if not isinstance(data, dict):
            raise self._error("Malformed FlareSolverr response", data)
        if data.get("status") != "ok":
            raise self._error("FlareSolverr returned non-ok status", data)
        return data

    @staticmethod
    def _error(message: str, details: Any) -> FlareSolverrError:
        return FlareSolverrError(f"{message}: {redact_payload(details)!r}")

    @staticmethod
    def _asset_error(
        message: str,
        details: Any,
        *,
        reason: str,
        status_code: int | None = None,
    ) -> FlareSolverrAssetError:
        return FlareSolverrAssetError(
            f"{message}: {redact_payload(details)!r}",
            reason=reason,
            status_code=status_code,
        )

    @staticmethod
    def _status_error(message: str, details: Any, *, status_code: int) -> FlareSolverrStatusError:
        return FlareSolverrStatusError(
            f"{message}: {redact_payload(details)!r}",
            status_code=status_code,
        )


def parse_proxy_url(proxy_url: str) -> ParsedProxy:
    parts = urlsplit(proxy_url)
    if parts.scheme.lower() not in SUPPORTED_PROXY_SCHEMES:
        raise FlareSolverrError(f"Unsupported proxy scheme: {parts.scheme}")
    if not parts.hostname:
        raise FlareSolverrError("Proxy URL must include a host")
    host = parts.hostname
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    clean_url = urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    username = unquote(parts.username) if parts.username is not None else None
    password = unquote(parts.password) if parts.password is not None else None
    return ParsedProxy(url=clean_url, username=username, password=password)


def _solution(payload: dict[str, Any]) -> dict[str, Any]:
    solution = payload.get("solution")
    if not isinstance(solution, dict):
        raise FlareSolverrError(f"Malformed FlareSolverr response: {redact_payload(payload)!r}")
    return solution


def _solution_response_body(solution: Mapping[str, Any]) -> tuple[str | None, bytes | None]:
    content: bytes | None = None
    encoded = solution.get("responseBase64")
    if isinstance(encoded, str):
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("invalid responseBase64") from exc

    response = solution.get("response")
    if isinstance(response, str):
        return response, content
    if content is not None:
        return content.decode("utf-8", errors="replace"), content
    return None, None


def _solution_headers(solution: Mapping[str, Any]) -> dict[str, str] | None:
    headers = solution.get("headers")
    if not isinstance(headers, Mapping):
        return None
    parsed: dict[str, str] = {}
    for key, value in headers.items():
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value is None:
            continue
        parsed[str(key)] = str(value)
    return parsed or None


def _solution_cookies(solution: Mapping[str, Any]) -> dict[str, str] | None:
    cookies = solution.get("cookies")
    parsed: dict[str, str] = {}
    if isinstance(cookies, Mapping):
        for name, value in cookies.items():
            parsed[str(name)] = str(value)
    elif isinstance(cookies, list):
        for cookie in cookies:
            if not isinstance(cookie, Mapping):
                continue
            name = cookie.get("name")
            value = cookie.get("value")
            if name is None or value is None:
                continue
            parsed[str(name)] = str(value)
    return parsed or None


def _solution_user_agent(solution: Mapping[str, Any]) -> str | None:
    value = solution.get("userAgent") or solution.get("user_agent")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _asset_request_headers(
    url: str,
    *,
    referer_url: str | None,
    base_url: str | None,
    user_agent: str | None = None,
) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent or BROWSER_USER_AGENT,
        "Accept": ASSET_ACCEPT,
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }
    referrer = _asset_context_url(url, referer_url=referer_url, base_url=base_url)
    if referrer is not None:
        headers["Referer"] = referrer
        origin = _origin(referrer)
        if origin is not None:
            headers["Origin"] = origin
            if origin == _origin(url):
                headers["Sec-Fetch-Site"] = "same-origin"
    return headers


def _headers_with_cookies(
    headers: dict[str, str],
    cookies: dict[str, str] | None,
) -> dict[str, str]:
    if not cookies:
        return headers
    merged = dict(headers)
    merged["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
    return merged


def _asset_context_url(
    url: str,
    *,
    referer_url: str | None,
    base_url: str | None,
) -> str | None:
    if _valid_absolute_url(referer_url):
        return str(referer_url)
    if _is_xchina_asset_url(url) and _valid_absolute_url(base_url):
        return _with_trailing_slash(str(base_url))
    return None


def _valid_absolute_url(url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _with_trailing_slash(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    if not path.endswith("/"):
        path = f"{path}/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _is_xchina_asset_url(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    return hostname in XCHINA_HOSTS or hostname.endswith(XCHINA_HOST_SUFFIXES)


def _looks_like_binary_asset_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".bmp",
            ".svg",
            ".mp4",
            ".mkv",
            ".mov",
            ".avi",
        )
    )


def _saw_status(errors: list[FlareSolverrError], status_code: int) -> bool:
    return any(getattr(error, "status_code", None) == status_code for error in errors)


def _last_status_code(errors: list[FlareSolverrError]) -> int | None:
    for error in reversed(errors):
        value = getattr(error, "status_code", None)
        if isinstance(value, int):
            return value
    return None
