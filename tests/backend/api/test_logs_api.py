from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app

ORIGIN = "http://testserver"


def test_logs_api_returns_recent_redacted_entries(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            logging.getLogger("tests.xona").warning(
                "probe token=raw-secret Authorization=Bearer raw-token"
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get("/api/logs/recent?limit=20")

    response = asyncio.run(run())

    assert response.status_code == 200
    body = response.json()
    assert "docker logs" in body["docker_logs_note"]
    text = response.text
    assert "raw-secret" not in text
    assert "raw-token" not in text
    assert any("probe" in entry["message"] for entry in body["entries"])


def test_logs_api_requires_auth_when_enabled(tmp_path: Path) -> None:
    settings = Settings(
        config_dir=tmp_path / "config",
        auth_enabled=True,
        auth_username="vito",
        auth_password_hash="hash",
    )

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get("/api/logs/recent")

    response = asyncio.run(run())

    assert response.status_code == 401
