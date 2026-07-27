from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from backend.app.api import settings as settings_api
from backend.app.core.settings import Settings
from backend.app.db.models import Setting
from backend.app.integrations.flaresolverr import FlareSolverrResponse
from backend.app.main import create_app
from backend.app.schemas.source import SourceSearchResult
from backend.app.services.settings_store import APP_SETTINGS_KEY


ORIGIN = "http://testserver"


class FakeFlareSolverr:
    async def request_get(self, url: str) -> FlareSolverrResponse:
        return FlareSolverrResponse(
            url=url,
            status_code=200,
            text="<html>ok</html>",
            headers={"set-cookie": "a=b"},
        )


class FakeXChina:
    async def search(self, query: str) -> list[SourceSearchResult]:
        return [
            SourceSearchResult(
                source_candidate_id="XC-001",
                title="Sample",
                url="https://xchina.example.test/videos/xc-001.html",
            )
        ]


class RecordingXChina:
    instances: list["RecordingXChina"] = []

    def __init__(
        self,
        _flaresolverr: object,
        _session: object,
        *,
        base_url: str,
        max_search_pages: int,
    ) -> None:
        self.base_url = base_url
        self.max_search_pages = max_search_pages
        RecordingXChina.instances.append(self)

    async def search(self, query: str) -> list[SourceSearchResult]:
        return [
            SourceSearchResult(
                source_candidate_id="XC-TEST",
                title=query,
                url=f"{self.base_url}/video/id-XC-TEST.html",
            )
        ]


class RecordingFlareSolverr:
    instances: list["RecordingFlareSolverr"] = []

    def __init__(self, endpoint: str, *, proxy_url: str | None = None) -> None:
        self.endpoint = endpoint
        self.proxy_url = proxy_url
        RecordingFlareSolverr.instances.append(self)

    async def close(self) -> None:
        return None


def test_settings_api_saves_sections_redacts_secrets_and_tests_connectors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    destination = root / "organized"
    destination.mkdir()
    cache_dir = tmp_path / "config" / "cache"
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        app.state.flaresolverr_client = FakeFlareSolverr()
        app.state.xchina_adapter = FakeXChina()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                update = await client.put(
                    "/api/settings",
                    json={
                        "storage": {"roots": [str(root)]},
                        "xchina": {
                            "flaresolverr_url": "http://solver:8191/custom",
                            "proxy_url": "http://user:pass@proxy.test:8080",
                            "cache_dir": str(cache_dir),
                            "max_search_pages": 123,
                        },
                        "emby": {
                            "enabled": True,
                            "server_url": "http://emby.test",
                            "api_key": "emby-secret",
                            "path_mappings": [
                                {
                                    "container_root": str(root),
                                    "emby_root": "/visible",
                                }
                            ],
                        },
                        "naming": {
                            "folder_templates": ["{studio}", "{title}"],
                            "filename_template": "{xchina_id} - {title}",
                        },
                        "metadata_assets": {"asset_policy": "strict"},
                        "organization_defaults": {
                            "destination_directory": str(destination),
                            "organization_mode": "hardlink",
                            "folder_templates": ["{studio}", "{xchina_id} - {title}"],
                            "filename_template": "{xchina_id} - {title}",
                            "asset_policy": "strict",
                            "include_source_snapshot": True,
                        },
                        "confidence_safety": {"confidence_threshold": 92},
                        "auth": {"enabled": False, "username": "vito"},
                    },
                    headers={"Origin": ORIGIN},
                )
                return {
                    "update": update,
                    "get": await client.get("/api/settings"),
                    "flare": await client.post(
                        "/api/settings/flaresolverr/test",
                        json={"url": "http://solver:8191/custom"},
                        headers={"Origin": ORIGIN},
                    ),
                    "xchina": await client.post(
                        "/api/settings/xchina/test",
                        json={"query": "sample"},
                        headers={"Origin": ORIGIN},
                    ),
                    "template": await client.post(
                        "/api/settings/templates/preview",
                        json={
                            "folder_templates": ["{studio}"],
                            "filename_template": "{xchina_id} - {title}",
                            "context": {
                                "studio": "Studio",
                                "title": "Sample",
                                "xchina_id": "XC-001",
                            },
                        },
                        headers={"Origin": ORIGIN},
                    ),
                }

    responses = asyncio.run(run())

    assert responses["update"].status_code == 200, responses["update"].text
    assert "emby-secret" not in responses["update"].text
    assert "pass" not in responses["get"].text
    assert responses["get"].json()["emby"]["api_key"] == "********"
    assert "manual_defaults" not in responses["get"].json()
    assert responses["get"].json()["organization_defaults"] == {
        "destination_directory": str(destination),
        "organization_mode": "hardlink",
        "folder_templates": ["{studio}", "{xchina_id} - {title}"],
        "filename_template": "{xchina_id} - {title}",
        "asset_policy": "strict",
        "include_source_snapshot": True,
    }
    assert responses["get"].json()["xchina"]["max_search_pages"] == 123
    assert responses["get"].json()["confidence_safety"]["confidence_threshold"] == 92
    assert responses["flare"].json()["status_code"] == 200
    assert responses["xchina"].json()["candidate_count"] == 1
    assert responses["template"].json()["filename"] == "XC-001 - Sample"


def test_xchina_test_uses_request_overrides_before_saved_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)
    RecordingXChina.instances.clear()
    RecordingFlareSolverr.instances.clear()
    monkeypatch.setattr(settings_api, "XChinaAdapter", RecordingXChina)
    monkeypatch.setattr(settings_api, "FlareSolverrClient", RecordingFlareSolverr)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                await client.put(
                    "/api/settings",
                    json={
                        "xchina": {
                            "base_url": "https://saved.xchina.test",
                            "flaresolverr_url": "http://saved-solver:8191/v1",
                            "proxy_url": "http://saved-proxy:8080",
                            "max_search_pages": 77,
                        }
                    },
                    headers={"Origin": ORIGIN},
                )
                return await client.post(
                    "/api/settings/xchina/test",
                    json={
                        "query": "override-query",
                        "base_url": "https://override.xchina.test",
                        "flaresolverr_url": "http://override-solver:8191/v1",
                        "proxy_url": None,
                        "max_search_pages": 3,
                    },
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert response.json()["candidate_count"] == 1
    assert RecordingFlareSolverr.instances[0].endpoint == "http://override-solver:8191/v1"
    assert RecordingFlareSolverr.instances[0].proxy_url is None
    assert RecordingXChina.instances[0].base_url == "https://override.xchina.test"
    assert RecordingXChina.instances[0].max_search_pages == 3


def test_xchina_test_empty_base_url_falls_back_to_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)
    RecordingXChina.instances.clear()
    monkeypatch.setattr(settings_api, "XChinaAdapter", RecordingXChina)
    monkeypatch.setattr(settings_api, "FlareSolverrClient", RecordingFlareSolverr)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.post(
                    "/api/settings/xchina/test",
                    json={
                        "query": "default-query",
                        "base_url": "",
                        "flaresolverr_url": "http://solver:8191/v1",
                    },
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert RecordingXChina.instances[0].base_url == "https://xchina.co"


def test_xchina_test_invalid_base_url_returns_controlled_diagnostic(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.post(
                    "/api/settings/xchina/test",
                    json={
                        "query": "invalid-base",
                        "base_url": "https://xchina.co/videos",
                        "flaresolverr_url": "http://solver:8191/v1",
                    },
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert "origin without path" in payload["diagnostics"]["error"]


def test_settings_api_rejects_xchina_base_url_with_path(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.put(
                    "/api/settings",
                    json={"xchina": {"base_url": "https://xchina.co/videos"}},
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 400
    assert "origin without path" in response.text


def test_settings_api_migrates_legacy_manual_defaults(tmp_path: Path) -> None:
    root = tmp_path / "media"
    destination = root / "organized"
    root.mkdir()
    destination.mkdir()
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                session.add(
                    Setting(
                        key=APP_SETTINGS_KEY,
                        value={
                            "storage": {"roots": [str(root)]},
                            "manual_defaults": {
                                "destination_directory": str(destination),
                                "organization_mode": "move",
                                "folder_templates": ["{studio}", "{title}"],
                                "filename_template": "{title}",
                                "asset_policy": "strict",
                                "include_source_snapshot": True,
                            },
                        },
                        secret=False,
                    )
                )
                session.commit()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                initial = await client.get("/api/settings")
                legacy_update = await client.put(
                    "/api/settings",
                    json={
                        "manual_defaults": {
                            "organization_mode": "hardlink",
                        },
                    },
                    headers={"Origin": ORIGIN},
                )
                return {
                    "get": initial,
                    "legacy_update": legacy_update,
                }

    responses = asyncio.run(run())

    assert responses["get"].status_code == 200
    assert "manual_defaults" not in responses["get"].json()
    assert responses["get"].json()["organization_defaults"] == {
        "destination_directory": str(destination),
        "organization_mode": "move",
        "folder_templates": ["{studio}", "{title}"],
        "filename_template": "{title}",
        "asset_policy": "strict",
        "include_source_snapshot": True,
    }
    assert responses["legacy_update"].status_code == 200, responses["legacy_update"].text
    assert "manual_defaults" not in responses["legacy_update"].json()
    assert (
        responses["legacy_update"].json()["organization_defaults"]["organization_mode"]
        == "hardlink"
    )


def test_settings_api_rejects_organization_default_destination_outside_storage_roots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.put(
                    "/api/settings",
                    json={
                        "storage": {"roots": [str(root)]},
                        "organization_defaults": {
                            "destination_directory": str(outside),
                        },
                    },
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 400
    assert "inside configured storage roots" in response.text
