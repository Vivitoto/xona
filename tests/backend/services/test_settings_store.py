from __future__ import annotations

from pathlib import Path

from backend.app.core.redaction import REDACTED
from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.settings_store import SettingsStore


def _sessionmaker(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return engine, get_sessionmaker(engine)


def test_settings_store_persists_typed_json_values(tmp_path: Path) -> None:
    engine, sessionmaker = _sessionmaker(tmp_path)
    try:
        with sessionmaker() as session:
            store = SettingsStore(session)
            store.set("scan", {"recursive": True, "limits": {"depth": 3}})
            session.commit()

        with sessionmaker() as session:
            store = SettingsStore(session)
            assert store.get("scan") == {"recursive": True, "limits": {"depth": 3}}
    finally:
        engine.dispose()


def test_settings_store_redacts_secret_values_on_public_read(tmp_path: Path) -> None:
    engine, sessionmaker = _sessionmaker(tmp_path)
    try:
        with sessionmaker() as session:
            store = SettingsStore(session)
            store.set("proxy", {"url": "http://user:pass@proxy.example:8080"}, secret=True)
            session.commit()

        with sessionmaker() as session:
            public_value = SettingsStore(session).get_public("proxy")
    finally:
        engine.dispose()

    rendered = repr(public_value)
    assert "user" not in rendered
    assert "pass" not in rendered
    assert REDACTED in rendered
