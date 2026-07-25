from __future__ import annotations

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


class FlareSolverrError(RuntimeError):
    pass


class FlareSolverrStatusError(FlareSolverrError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FlareSolverrResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str] | None = None


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
        text = solution.get("response")
        if not isinstance(text, str):
            raise self._error("Malformed FlareSolverr response", result)
        headers = solution.get("headers")
        return FlareSolverrResponse(
            url=str(solution.get("url") or url),
            status_code=status_code,
            text=text,
            headers=headers if isinstance(headers, dict) else None,
        )

    async def request_asset(self, url: str, *, session_id: str | None = None) -> FetchedAsset:
        try:
            response = await self._asset_client().get(url)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise self._error("Asset request timeout", {"url": url, "proxy": self._proxy.session_payload() if self._proxy else None}) from exc
        except httpx.HTTPError as exc:
            raise self._error("Asset request failed", {"url": url, "proxy": self._proxy.session_payload() if self._proxy else None}) from exc
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

    def _asset_client(self) -> httpx.AsyncClient:
        if self._asset_http_client is None:
            self._asset_http_client = httpx.AsyncClient(
                timeout=httpx.Timeout((self._max_timeout_ms / 1000) + 10),
                follow_redirects=True,
                proxy=self._proxy.httpx_url() if self._proxy is not None else None,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
                    ),
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
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
