from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app


ORIGIN = "http://testserver"


def test_watch_rule_api_crud_and_scan_now(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    (source / "movie.mkv").write_bytes(b"movie")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                settings_update = await client.put(
                    "/api/settings",
                    json={
                        "organization_defaults": {
                            "destination_directory": str(destination),
                            "organization_mode": "hardlink",
                            "folder_templates": ["{studio}", "{xchina_id}"],
                            "filename_template": "{xchina_id} - {title}",
                            "asset_policy": "lenient",
                            "include_source_snapshot": True,
                        },
                    },
                    headers={"Origin": ORIGIN},
                )
                created = await client.post(
                    "/api/watch-rules",
                    json={
                        "source_directory": str(source),
                        "include_patterns": ["*.mkv"],
                    },
                    headers={"Origin": ORIGIN},
                )
                rule_id = created.json()["rule_id"]
                return {
                    "settings_update": settings_update,
                    "created": created,
                    "listed": await client.get("/api/watch-rules"),
                    "updated": await client.put(
                        f"/api/watch-rules/{rule_id}",
                        json={"enabled": False},
                        headers={"Origin": ORIGIN},
                    ),
                    "scan": await client.post(
                        f"/api/watch-rules/{rule_id}/scan-now",
                        headers={"Origin": ORIGIN},
                    ),
                    "deleted": await client.delete(
                        f"/api/watch-rules/{rule_id}",
                        headers={"Origin": ORIGIN},
                    ),
                }

    responses = asyncio.run(run())
    assert responses["settings_update"].status_code == 200, responses["settings_update"].text
    assert responses["created"].status_code == 201, responses["created"].text
    assert responses["created"].json()["destination_directory"] == str(destination)
    assert responses["created"].json()["organization_mode"] == "hardlink"
    assert responses["created"].json()["folder_templates"] == ["{studio}", "{xchina_id}"]
    assert responses["created"].json()["filename_template"] == "{xchina_id} - {title}"
    assert responses["created"].json()["asset_policy"] == "lenient"
    assert responses["listed"].json()["rules"][0]["source_directory"] == str(source)
    assert responses["updated"].json()["enabled"] is False
    assert responses["scan"].status_code == 200
    assert responses["scan"].json()["enqueued_jobs"] == [1]
    assert responses["deleted"].status_code == 204
