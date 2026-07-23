from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app
from backend.app.services.settings_store import SettingsStore


ORIGIN = "http://testserver"


def test_settings_secret_omission_keeps_value_and_placeholder_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> tuple[httpx.Response, httpx.Response, str | None]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                SettingsStore(session).update_app_settings(
                    {
                        "emby": {
                            "enabled": True,
                            "server_url": "http://emby.test",
                            "api_key": "old-secret",
                            "path_mappings": [
                                {"container_root": str(root), "emby_root": "/visible"}
                            ],
                        }
                    }
                )
                session.commit()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                omitted = await client.put(
                    "/api/settings",
                    json={"emby": {"server_url": "http://emby2.test"}},
                    headers={"Origin": ORIGIN},
                )
                placeholder = await client.put(
                    "/api/settings",
                    json={"emby": {"api_key": "********"}},
                    headers={"Origin": ORIGIN},
                )
            with app.state.sessionmaker() as session:
                stored = SettingsStore(session).emby_settings().get("api_key")
            return omitted, placeholder, stored

    omitted, placeholder, stored = asyncio.run(run())

    assert omitted.status_code == 200, omitted.text
    assert placeholder.status_code == 400
    assert stored == "old-secret"
