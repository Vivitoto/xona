from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from backend.app.integrations.flaresolverr import FlareSolverrClient, FlareSolverrError


def _ok_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_request_get_calls_configured_endpoint_exactly_without_appending_v1() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), __import__("json").loads(request.content)))
        return _ok_response({"status": "ok", "solution": {"status": 200, "response": "ok"}})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient("http://solver.example/custom", http_client=http)
            result = await client.request_get("https://target.example/item")
            assert result.text == "ok"

    asyncio.run(run())

    assert seen == [
        (
            "http://solver.example/custom",
            {"cmd": "request.get", "url": "https://target.example/item", "maxTimeout": 60000},
        )
    ]


def test_unauthenticated_proxy_is_sent_on_request_get() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(__import__("json").loads(request.content))
        return _ok_response({"status": "ok", "solution": {"status": 200, "response": "ok"}})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/v1",
                proxy_url="http://proxy.example:8080",
                http_client=http,
            )
            await client.request_get("https://target.example/item")

    asyncio.run(run())

    assert payloads[0]["proxy"] == {"url": "http://proxy.example:8080"}


def test_credentialed_http_proxy_credentials_are_only_sent_on_session_create() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        payloads.append(payload)
        if payload["cmd"] == "sessions.create":
            return _ok_response({"status": "ok", "session": "session-id"})
        return _ok_response({"status": "ok", "solution": {"status": 200, "response": "ok"}})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/solver",
                proxy_url="http://proxy-user:proxy-pass@proxy.example:8080",
                http_client=http,
            )
            await client.request_get("https://target.example/item")

    asyncio.run(run())

    assert payloads[0] == {
        "cmd": "sessions.create",
        "proxy": {
            "url": "http://proxy.example:8080",
            "username": "proxy-user",
            "password": "proxy-pass",
        },
    }
    assert payloads[1]["cmd"] == "request.get"
    assert payloads[1]["session"] == "session-id"
    assert "proxy" not in payloads[1]
    assert "proxy-user" not in repr(payloads[1])
    assert "proxy-pass" not in repr(payloads[1])


def test_credentialed_socks_proxy_session_payload_is_parsed() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        payloads.append(payload)
        return _ok_response({"status": "ok", "session": "sock-session"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/custom",
                proxy_url="socks5://sock-user:sock-pass@proxy.example:1080",
                http_client=http,
            )
            assert await client.create_session() == "sock-session"

    asyncio.run(run())

    assert payloads == [
        {
            "cmd": "sessions.create",
            "proxy": {
                "url": "socks5://proxy.example:1080",
                "username": "sock-user",
                "password": "sock-pass",
            },
        }
    ]


def test_failures_redact_credentials() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(
            {
                "status": "error",
                "message": "failed http://proxy-user:proxy-pass@proxy.example:8080",
            }
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/custom",
                proxy_url="http://proxy-user:proxy-pass@proxy.example:8080",
                http_client=http,
            )
            with pytest.raises(FlareSolverrError) as exc:
                await client.request_get("https://target.example/item")
            rendered = str(exc.value)
            assert "proxy-user" not in rendered
            assert "proxy-pass" not in rendered
            assert "********" in rendered

    asyncio.run(run())


def test_asset_requests_use_direct_http_client_not_flaresolverr_preview_page() -> None:
    solver_seen: list[dict[str, Any]] = []
    asset_seen: list[str] = []

    async def solver_handler(request: httpx.Request) -> httpx.Response:
        solver_seen.append(__import__("json").loads(request.content))
        return _ok_response({"status": "ok", "solution": {"status": 200, "response": "html"}})

    async def asset_handler(request: httpx.Request) -> httpx.Response:
        asset_seen.append(str(request.url))
        return httpx.Response(
            200,
            content=b"\xff\xd8\xffjpg-bytes",
            headers={"Content-Type": "image/jpeg"},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(solver_handler)) as http:
            async with httpx.AsyncClient(transport=httpx.MockTransport(asset_handler)) as asset_http:
                client = FlareSolverrClient(
                    "http://solver.example/custom",
                    proxy_url="http://proxy.example:8080",
                    http_client=http,
                    asset_http_client=asset_http,
                )
                result = await client.request_asset("https://target.example/asset.jpg")
                assert result.content == b"\xff\xd8\xffjpg-bytes"
                assert result.content_type == "image/jpeg"

    asyncio.run(run())

    assert solver_seen == []
    assert asset_seen == ["https://target.example/asset.jpg"]


def test_request_asset_returns_fetched_asset_with_header_content_type() -> None:
    async def asset_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\npng-bytes",
            headers={"Content-Type": "image/png; charset=binary"},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(asset_handler)) as asset_http:
            client = FlareSolverrClient(
                "http://solver.example/custom",
                asset_http_client=asset_http,
            )
            result = await client.request_asset("https://target.example/asset")
            assert result.url == "https://target.example/asset"
            assert result.content == b"\x89PNG\r\n\x1a\npng-bytes"
            assert result.content_type == "image/png"

    asyncio.run(run())
