from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app


ORIGIN = "http://testserver"


class FakeEmbyClient:
    async def test_connection(self):
        return {
            "ok": True,
            "authorized": True,
            "server_version": "4.8.0",
            "server_name": "Emby",
            "libraries": [{"id": "lib-1", "name": "Movies", "locations": ["/visible"]}],
            "diagnostics": {"api_key": "secret"},
        }

    async def libraries(self):
        return [{"id": "lib-1", "name": "Movies", "locations": ["/visible"]}]


def test_emby_api_redacts_keys_and_lists_libraries(tmp_path: Path) -> None:
    settings = Settings(
        config_dir=tmp_path / "config",
        auth_enabled=False,
        emby_server_url="http://emby.test",
        emby_api_key="secret-key",
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        app.state.emby_client = FakeEmbyClient()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return {
                    "test": await client.post(
                        "/api/emby/test",
                        json={"server_url": "http://emby.test", "api_key": "secret-key"},
                        headers={"Origin": ORIGIN},
                    ),
                    "libraries": await client.get("/api/emby/libraries"),
                }

    responses = asyncio.run(run())

    assert responses["test"].status_code == 200, responses["test"].text
    assert "secret-key" not in responses["test"].text
    assert responses["test"].json()["diagnostics"]["api_key"] == "********"
    assert responses["libraries"].json()["libraries"][0]["name"] == "Movies"
