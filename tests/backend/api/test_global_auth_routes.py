from __future__ import annotations

from pathlib import Path

import asyncio
import httpx

from backend.app.api.auth import PasswordHasher
from backend.app.core.settings import Settings
from backend.app.main import AUTH_ENDPOINT_PATHS, create_app


ORIGIN = "http://testserver"
USERNAME = "vito"
PASSWORD = "correct horse battery staple"

PROTECTED_API_PREFIXES = (
    "/api/actors",
    "/api/emby",
    "/api/history",
    "/api/jobs",
    "/api/logs",
    "/api/local-metadata",
    "/api/manual",
    "/api/plans",
    "/api/settings",
    "/api/storage-roots",
    "/api/watch-rules",
)


def _settings(tmp_path: Path, *, auth_enabled: bool = True) -> Settings:
    return Settings(
        config_dir=tmp_path / "config",
        auth_enabled=auth_enabled,
        auth_username=USERNAME,
        auth_password_hash=PasswordHasher(rounds=4).hash(PASSWORD),
    )


def test_every_api_route_is_auth_or_protected(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    unclassified: list[str] = []
    for path in app.openapi()["paths"]:
        if not path.startswith("/api/"):
            continue
        if path in AUTH_ENDPOINT_PATHS:
            continue
        if path.startswith(PROTECTED_API_PREFIXES):
            continue
        unclassified.append(path)

    assert unclassified == []


def test_storage_root_routes_require_authentication_when_enabled(tmp_path: Path) -> None:
    async def run() -> tuple[httpx.Response, httpx.Response]:
        app = create_app(_settings(tmp_path))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return (
                    await client.get("/api/storage-roots"),
                    await client.post(
                        "/api/storage-roots/validate",
                        json={"path": str(tmp_path)},
                        headers={"Origin": ORIGIN},
                    ),
                )

    list_response, validate_response = asyncio.run(run())

    assert list_response.status_code == 401
    assert validate_response.status_code == 401


def test_storage_root_routes_are_available_when_auth_disabled(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    settings = _settings(tmp_path, auth_enabled=False)
    settings.storage_roots = (media_root,)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get("/api/storage-roots")

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.json()["roots"][0]["path"] == str(media_root)
