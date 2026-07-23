from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.watch_rules import WatchRuleCreate
from backend.app.services.watch_rules import WatchRuleService


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def test_event_storm_and_database_constraint_prevent_duplicate_active_jobs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            service = WatchRuleService(settings, session)
            rule = service.create_rule(
                WatchRuleCreate(
                    source_directory=source,
                    destination_directory=destination,
                )
            )
            first = service.enqueue_once(
                rule,
                media_identity="inode:1:2",
                last_seen_path=source / "movie.mkv",
                size_bytes=10,
                mtime_ns=123,
                stable_count=2,
            )
            second = service.enqueue_once(
                rule,
                media_identity="inode:1:2",
                last_seen_path=source / "movie.mkv",
                size_bytes=10,
                mtime_ns=123,
                stable_count=2,
            )
            assert second.id == first.id

            session.add(
                Job(
                    rule_id=rule.rule_id,
                    media_identity="inode:1:2",
                    manual=False,
                    state="waiting_stable",
                    payload={},
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
    finally:
        engine.dispose()
