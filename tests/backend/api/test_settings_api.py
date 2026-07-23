from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.integrations.flaresolverr import FlareSolverrResponse
from backend.app.main import create_app
from backend.app.schemas.source import SourceSearchResult


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


def test_settings_api_saves_sections_redacts_secrets_and_tests_connectors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
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
    assert responses["get"].json()["confidence_safety"]["confidence_threshold"] == 92
    assert responses["flare"].json()["status_code"] == 200
    assert responses["xchina"].json()["candidate_count"] == 1
    assert responses["template"].json()["filename"] == "XC-001 - Sample"
