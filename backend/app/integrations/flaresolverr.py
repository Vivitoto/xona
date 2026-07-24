from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from backend.app.core.redaction import redact_payload


SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5"}


class FlareSolverrError(RuntimeError):
    pass


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


class FlareSolverrClient:
    def __init__(
        self,
        endpoint: str,
        *,
        proxy_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        max_timeout_ms: int = 60_000,
    ) -> None:
        self._endpoint = endpoint
        self._proxy = parse_proxy_url(proxy_url) if proxy_url else None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout((max_timeout_ms / 1000) + 10)
        )
        self._owns_http_client = http_client is None
        self._max_timeout_ms = max_timeout_ms
        self._credentialed_session_id: str | None = None

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "FlareSolverrClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def request_get(self, url: str, *, session_id: str | None = None) -> FlareSolverrResponse:
        payload = await self._request_payload(url, session_id=session_id)
        result = await self._post(payload)
        solution = _solution(result)
        status_code = int(solution.get("status") or 0)
        text = solution.get("response")
        if not isinstance(text, str):
            raise self._error("Malformed FlareSolverr response", result)
        if status_code >= 400:
            reason = "Cloudflare block" if status_code in {403, 503} else "HTTP error"
            raise self._error(reason, result)
        headers = solution.get("headers")
        return FlareSolverrResponse(
            url=str(solution.get("url") or url),
            status_code=status_code,
            text=text,
            headers=headers if isinstance(headers, dict) else None,
        )

    async def request_asset(self, url: str, *, session_id: str | None = None) -> bytes:
        payload = await self._request_payload(url, session_id=session_id)
        result = await self._post(payload)
        solution = _solution(result)
        status_code = int(solution.get("status") or 0)
        if status_code >= 400:
            raise self._error("Asset request failed", result)
        response = solution.get("response")
        if not isinstance(response, str):
            raise self._error("Malformed asset response", result)
        if solution.get("encoding") == "base64":
            try:
                return base64.b64decode(response)
            except ValueError as exc:
                raise self._error("Malformed base64 asset response", result) from exc
        return response.encode("utf-8")

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

    async def _request_payload(
        self, url: str, *, session_id: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self._max_timeout_ms,
        }
        if session_id is not None:
            payload["session"] = session_id
            return payload
        if self._proxy is None:
            return payload
        if self._proxy.credentialed:
            if self._credentialed_session_id is None:
                self._credentialed_session_id = await self.create_session()
            payload["session"] = self._credentialed_session_id
        else:
            payload["proxy"] = self._proxy.request_payload()
        return payload

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
