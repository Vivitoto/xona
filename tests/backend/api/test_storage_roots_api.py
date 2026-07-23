from __future__ import annotations

from pathlib import Path

import asyncio
import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app


ORIGIN = "http://testserver"


def test_storage_roots_crud_browse_and_validate_api(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "movie.mp4").write_text("synthetic", encoding="utf-8")
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                created = await client.post(
                    "/api/storage-roots",
                    json={"path": str(media_root)},
                    headers={"Origin": ORIGIN},
                )
                root_id = created.json().get("id")

                return {
                    "created": created,
                    "listed": await client.get("/api/storage-roots"),
                    "browsed": await client.get(
                        f"/api/storage-roots/browse?root_id={root_id}"
                    ),
                    "traversal": await client.get(
                        f"/api/storage-roots/browse?root_id={root_id}&path=..%2Foutside"
                    ),
                    "valid": await client.post(
                        "/api/storage-roots/validate",
                        json={"path": str(media_root / "movie.mp4")},
                        headers={"Origin": ORIGIN},
                    ),
                    "updated": await client.put(
                        f"/api/storage-roots/{root_id}",
                        json={"enabled": False},
                        headers={"Origin": ORIGIN},
                    ),
                    "deleted": await client.delete(
                        f"/api/storage-roots/{root_id}",
                        headers={"Origin": ORIGIN},
                    ),
                }

    responses = asyncio.run(run())
    created = responses["created"]
    assert created.status_code == 201, created.text

    listed = responses["listed"]
    assert listed.status_code == 200
    assert listed.json()["roots"][0]["path"] == str(media_root)

    browsed = responses["browsed"]
    assert browsed.status_code == 200
    assert browsed.json()["entries"][0]["name"] == "movie.mp4"

    traversal = responses["traversal"]
    assert traversal.status_code == 400

    valid = responses["valid"]
    assert valid.status_code == 200
    assert valid.json()["inside_root"] is True

    updated = responses["updated"]
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    deleted = responses["deleted"]
    assert deleted.status_code == 204
