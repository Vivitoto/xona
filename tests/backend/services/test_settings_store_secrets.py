from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.settings_store import SettingsStore, SettingsUpdateError


def _sessionmaker(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return engine, get_sessionmaker(engine)


def test_app_settings_redact_and_reject_secret_placeholders(tmp_path: Path) -> None:
    engine, sessionmaker = _sessionmaker(tmp_path)
    try:
        with sessionmaker() as session:
            store = SettingsStore(session)
            public = store.update_app_settings(
                {"emby": {"api_key": "real-secret", "server_url": "http://emby.test"}}
            )
            assert public["emby"]["api_key"] == "********"
            assert store.emby_settings()["api_key"] == "real-secret"
            with pytest.raises(SettingsUpdateError):
                store.update_app_settings({"emby": {"api_key": "********"}})
    finally:
        engine.dispose()
