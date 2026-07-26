from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx
import pytest

from backend.app.integrations.flaresolverr import (
    FlareSolverrAssetError,
    FlareSolverrClient,
    FlareSolverrError,
)


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


def test_proxy_request_get_reuses_persistent_session_and_closes_it() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        payloads.append(payload)
        if payload["cmd"] == "sessions.create":
            return _ok_response({"status": "ok", "session": "session-id"})
        if payload["cmd"] == "sessions.destroy":
            return _ok_response({"status": "ok"})
        assert payload["cmd"] == "request.get"
        assert payload["session"] == "session-id"
        assert "proxy" not in payload
        return _ok_response({"status": "ok", "solution": {"status": 200, "response": "ok"}})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/v1",
                proxy_url="http://proxy.example:8080",
                http_client=http,
            )
            await client.request_get("https://target.example/item")
            await client.request_get("https://target.example/second")
            await client.close()

    asyncio.run(run())

    assert payloads == [
        {
            "cmd": "sessions.create",
            "proxy": {"url": "http://proxy.example:8080"},
        },
        {
            "cmd": "request.get",
            "url": "https://target.example/item",
            "maxTimeout": 60000,
            "session": "session-id",
        },
        {
            "cmd": "request.get",
            "url": "https://target.example/second",
            "maxTimeout": 60000,
            "session": "session-id",
        },
        {"cmd": "sessions.destroy", "session": "session-id"},
    ]


def test_proxy_request_get_recreates_session_after_request_failure() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        payloads.append(payload)
        if payload["cmd"] == "sessions.create":
            session_number = sum(1 for item in payloads if item.get("cmd") == "sessions.create")
            return _ok_response({"status": "ok", "session": f"session-{session_number}"})
        if payload["cmd"] == "request.get" and payload.get("session") == "session-1":
            return httpx.Response(500, json={"status": "error", "message": "blocked"})
        if payload["cmd"] == "request.get" and payload.get("session") == "session-2":
            return _ok_response({"status": "ok", "solution": {"status": 200, "response": "ok"}})
        if payload["cmd"] == "sessions.destroy":
            return _ok_response({"status": "ok"})
        raise AssertionError(f"unexpected payload: {payload}")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/v1",
                proxy_url="http://proxy.example:8080",
                http_client=http,
            )
            result = await client.request_get("https://target.example/item")
            assert result.text == "ok"
            await client.close()

    asyncio.run(run())

    assert payloads == [
        {
            "cmd": "sessions.create",
            "proxy": {"url": "http://proxy.example:8080"},
        },
        {
            "cmd": "request.get",
            "url": "https://target.example/item",
            "maxTimeout": 60000,
            "session": "session-1",
        },
        {"cmd": "sessions.destroy", "session": "session-1"},
        {
            "cmd": "sessions.create",
            "proxy": {"url": "http://proxy.example:8080"},
        },
        {
            "cmd": "request.get",
            "url": "https://target.example/item",
            "maxTimeout": 60000,
            "session": "session-2",
        },
        {"cmd": "sessions.destroy", "session": "session-2"},
    ]


def test_proxy_request_get_recreates_session_after_cloudflare_status() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        payloads.append(payload)
        if payload["cmd"] == "sessions.create":
            session_number = sum(1 for item in payloads if item.get("cmd") == "sessions.create")
            return _ok_response({"status": "ok", "session": f"session-{session_number}"})
        if payload["cmd"] == "request.get" and payload.get("session") == "session-1":
            return _ok_response({"status": "ok", "solution": {"status": 503, "response": "blocked"}})
        if payload["cmd"] == "request.get" and payload.get("session") == "session-2":
            return _ok_response({"status": "ok", "solution": {"status": 200, "response": "ok"}})
        if payload["cmd"] == "sessions.destroy":
            return _ok_response({"status": "ok"})
        raise AssertionError(f"unexpected payload: {payload}")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = FlareSolverrClient(
                "http://solver.example/v1",
                proxy_url="http://proxy.example:8080",
                http_client=http,
            )
            result = await client.request_get("https://target.example/item")
            assert result.text == "ok"
            await client.close()

    asyncio.run(run())

    assert payloads == [
        {"cmd": "sessions.create", "proxy": {"url": "http://proxy.example:8080"}},
        {
            "cmd": "request.get",
            "url": "https://target.example/item",
            "maxTimeout": 60000,
            "session": "session-1",
        },
        {"cmd": "sessions.destroy", "session": "session-1"},
        {"cmd": "sessions.create", "proxy": {"url": "http://proxy.example:8080"}},
        {
            "cmd": "request.get",
            "url": "https://target.example/item",
            "maxTimeout": 60000,
            "session": "session-2",
        },
        {"cmd": "sessions.destroy", "session": "session-2"},
    ]


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


def test_request_asset_sends_browser_headers_with_xchina_context() -> None:
    seen: dict[str, str] = {}

    async def asset_handler(request: httpx.Request) -> httpx.Response:
        seen.update(
            {
                "accept": request.headers.get("accept", ""),
                "accept_language": request.headers.get("accept-language", ""),
                "origin": request.headers.get("origin", ""),
                "referer": request.headers.get("referer", ""),
                "sec_fetch_dest": request.headers.get("sec-fetch-dest", ""),
                "sec_fetch_mode": request.headers.get("sec-fetch-mode", ""),
                "user_agent": request.headers.get("user-agent", ""),
            }
        )
        return httpx.Response(
            200,
            content=b"RIFF\x0c\x00\x00\x00WEBPwebp-bytes",
            headers={"Content-Type": "image/webp"},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(asset_handler)) as asset_http:
            client = FlareSolverrClient(
                "http://solver.example/custom",
                asset_http_client=asset_http,
            )
            await client.request_asset(
                "https://upload.xchina.io/video/cover.webp?token=secret-token",
                referer_url="https://www.xchina.co/videos/id-XC001.html",
                base_url="https://www.xchina.co",
            )

    asyncio.run(run())

    assert "Mozilla/5.0" in seen["user_agent"]
    assert "image/webp" in seen["accept"]
    assert seen["accept_language"] == "en-US,en;q=0.9"
    assert seen["referer"] == "https://www.xchina.co/videos/id-XC001.html"
    assert seen["origin"] == "https://www.xchina.co"
    assert seen["sec_fetch_dest"] == "image"
    assert seen["sec_fetch_mode"] == "no-cors"


def test_request_asset_retries_direct_with_flaresolverr_cookies_after_403() -> None:
    solver_seen: list[dict[str, Any]] = []
    asset_seen: list[dict[str, str]] = []

    async def solver_handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        solver_seen.append(payload)
        assert payload["url"] == "https://www.xchina.co/videos/id-XC001.html"
        return _ok_response(
            {
                "status": "ok",
                "solution": {
                    "status": 200,
                    "url": "https://www.xchina.co/videos/id-XC001.html",
                    "response": "<html>detail</html>",
                    "userAgent": "Solved Browser UA",
                    "cookies": [{"name": "cf_clearance", "value": "solved-cookie"}],
                },
            }
        )

    async def asset_handler(request: httpx.Request) -> httpx.Response:
        asset_seen.append(
            {
                "cookie": request.headers.get("cookie", ""),
                "referer": request.headers.get("referer", ""),
                "user_agent": request.headers.get("user-agent", ""),
            }
        )
        if len(asset_seen) == 1:
            return httpx.Response(403, content=b"forbidden")
        assert request.headers["user-agent"] == "Solved Browser UA"
        assert "cf_clearance=solved-cookie" in request.headers.get("cookie", "")
        return httpx.Response(
            200,
            content=b"\xff\xd8\xffjpeg-bytes",
            headers={"Content-Type": "image/jpeg"},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(solver_handler)) as http:
            async with httpx.AsyncClient(transport=httpx.MockTransport(asset_handler)) as asset_http:
                client = FlareSolverrClient(
                    "http://solver.example/custom",
                    http_client=http,
                    asset_http_client=asset_http,
                )
                result = await client.request_asset(
                    "https://upload.xchina.io/video/cover.jpg",
                    referer_url="https://www.xchina.co/videos/id-XC001.html",
                    base_url="https://www.xchina.co",
                )
                assert result.content == b"\xff\xd8\xffjpeg-bytes"
                assert result.content_type == "image/jpeg"

    asyncio.run(run())

    assert [payload["cmd"] for payload in solver_seen] == ["request.get"]
    assert len(asset_seen) == 2
    assert asset_seen[0]["referer"] == "https://www.xchina.co/videos/id-XC001.html"
    assert asset_seen[1]["user_agent"] == "Solved Browser UA"


def test_request_asset_can_return_flaresolverr_binary_response_when_direct_retry_fails() -> None:
    solver_seen: list[str] = []

    async def solver_handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        solver_seen.append(payload["url"])
        if payload["url"] == "https://www.xchina.co/videos/id-XC001.html":
            return _ok_response(
                {
                    "status": "ok",
                    "solution": {
                        "status": 200,
                        "response": "<html>detail</html>",
                        "cookies": [{"name": "cf_clearance", "value": "solved-cookie"}],
                    },
                }
            )
        return _ok_response(
            {
                "status": "ok",
                "solution": {
                    "status": 200,
                    "url": "https://upload.xchina.io/video/cover.jpg",
                    "headers": {"Content-Type": "image/jpeg"},
                    "responseBase64": base64.b64encode(b"\xff\xd8\xffsolver-jpeg").decode(),
                },
            }
        )

    async def asset_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"blocked")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(solver_handler)) as http:
            async with httpx.AsyncClient(transport=httpx.MockTransport(asset_handler)) as asset_http:
                client = FlareSolverrClient(
                    "http://solver.example/custom",
                    http_client=http,
                    asset_http_client=asset_http,
                )
                result = await client.request_asset(
                    "https://upload.xchina.io/video/cover.jpg",
                    referer_url="https://www.xchina.co/videos/id-XC001.html",
                    base_url="https://www.xchina.co",
                )
                assert result.content == b"\xff\xd8\xffsolver-jpeg"
                assert result.content_type == "image/jpeg"

    asyncio.run(run())

    assert solver_seen == [
        "https://www.xchina.co/videos/id-XC001.html",
        "https://upload.xchina.io/video/cover.jpg",
    ]


def test_request_asset_classifies_persistent_403_as_hotlink_forbidden_and_redacts() -> None:
    async def solver_handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(
            {
                "status": "ok",
                "solution": {
                    "status": 200,
                    "response": "<html>detail</html>",
                    "userAgent": "Solved Browser UA",
                    "cookies": [{"name": "cf_clearance", "value": "secret-cookie"}],
                },
            }
        )

    async def asset_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"forbidden")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(solver_handler)) as http:
            async with httpx.AsyncClient(transport=httpx.MockTransport(asset_handler)) as asset_http:
                client = FlareSolverrClient(
                    "http://solver.example/custom",
                    http_client=http,
                    asset_http_client=asset_http,
                )
                with pytest.raises(FlareSolverrAssetError) as exc:
                    await client.request_asset(
                        "https://upload.xchina.io/video/cover.jpg?token=secret-token",
                        referer_url="https://www.xchina.co/videos/id-XC001.html",
                        base_url="https://www.xchina.co",
                    )
                assert exc.value.reason == "hotlink_forbidden"
                assert exc.value.status_code == 403
                rendered = str(exc.value)
                assert "secret-token" not in rendered
                assert "secret-cookie" not in rendered
                assert "********" in rendered

    asyncio.run(run())
