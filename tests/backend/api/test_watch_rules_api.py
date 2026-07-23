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
                created = await client.post(
                    "/api/watch-rules",
                    json={
                        "source_directory": str(source),
                        "destination_directory": str(destination),
                        "include_patterns": ["*.mkv"],
                        "organization_mode": "copy",
                    },
                    headers={"Origin": ORIGIN},
                )
                rule_id = created.json()["rule_id"]
                return {
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
    assert responses["created"].status_code == 201, responses["created"].text
    assert responses["listed"].json()["rules"][0]["source_directory"] == str(source)
    assert responses["updated"].json()["enabled"] is False
    assert responses["scan"].status_code == 200
    assert responses["scan"].json()["enqueued_jobs"] == [1]
    assert responses["deleted"].status_code == 204
