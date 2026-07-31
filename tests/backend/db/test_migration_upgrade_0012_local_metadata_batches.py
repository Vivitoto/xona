from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command

from backend.app.db.migrations import _alembic_config, run_migrations


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def test_upgrade_from_0011_to_head_creates_local_metadata_batches(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "xona.db"
    database_url = _sqlite_url(database_path)

    command.upgrade(_alembic_config(database_url), "0011_emby_links")
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

    assert "local_metadata_batches" in tables
    assert "local_metadata_batch_items" in tables
    assert "ix_local_metadata_batches_status" in indexes
    assert "ix_local_metadata_batch_items_batch_status" in indexes
    assert revision == "0012_local_metadata_batches"
