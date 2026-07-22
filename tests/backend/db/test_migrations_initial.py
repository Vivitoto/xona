from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.settings import Settings
from backend.app.db.base import Base
from backend.app.db.migrations import run_migrations
from backend.app.main import create_app


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def _table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def _alembic_revision(database_path: Path) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def test_run_migrations_with_database_url_creates_initial_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "xona.db"

    run_migrations(database_url=_sqlite_url(database_path))

    assert {"settings", "storage_roots", "alembic_version"} <= _table_names(
        database_path
    )
    assert _alembic_revision(database_path).startswith("0001")


def test_run_migrations_with_settings_creates_database_under_config_dir(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    settings = Settings(config_dir=config_dir)

    run_migrations(settings=settings)

    database_path = config_dir / "xona.db"
    assert database_path.is_file()
    assert {"settings", "storage_roots", "alembic_version"} <= _table_names(
        database_path
    )


def test_run_migrations_does_not_use_metadata_create_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_create_all(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "run_migrations must use Alembic, not Base.metadata.create_all"
        )

    database_path = tmp_path / "xona.db"
    monkeypatch.setattr(Base.metadata, "create_all", fail_create_all)

    run_migrations(database_url=_sqlite_url(database_path))

    assert {"settings", "storage_roots", "alembic_version"} <= _table_names(
        database_path
    )


def test_fastapi_lifespan_runs_migrations_with_injected_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.db.migrations as migration_module
    import backend.app.main as main_module

    settings = Settings(config_dir=tmp_path / "config")
    calls: list[Settings] = []

    def record_run_migrations(
        *,
        settings: Settings | None = None,
        database_url: str | None = None,
    ) -> None:
        assert database_url is None
        assert settings is not None
        calls.append(settings)

    monkeypatch.setattr(migration_module, "run_migrations", record_run_migrations)
    if hasattr(main_module, "run_migrations"):
        monkeypatch.setattr(main_module, "run_migrations", record_run_migrations)

    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == [settings]


def test_run_migrations_requires_exactly_one_target(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config")

    with pytest.raises(ValueError, match="database_url|settings"):
        run_migrations()

    with pytest.raises(ValueError, match="database_url|settings"):
        run_migrations(database_url=_sqlite_url(tmp_path / "xona.db"), settings=settings)
