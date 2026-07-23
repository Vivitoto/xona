from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command

from backend.app.db.migrations import _alembic_config, run_migrations


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def test_upgrade_from_0010_to_head_creates_emby_links(tmp_path: Path) -> None:
    database_path = tmp_path / "xona.db"
    database_url = _sqlite_url(database_path)

    command.upgrade(_alembic_config(database_url), "0010_watch_monitor_state")
    run_migrations(database_url=database_url)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]

    assert "emby_links" in tables
    assert "ix_emby_links_job_id" in indexes
    assert "ix_emby_links_actor_id" in indexes
    assert revision == "0011_emby_links"
