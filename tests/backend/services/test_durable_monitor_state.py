from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import MonitorMediaState
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.watch_rules import WatchRuleCreate
from backend.app.services.watch_rules import WatchRuleService


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def test_monitor_state_persists_per_rule_and_media_identity(tmp_path: Path) -> None:
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
            job = service.enqueue_once(
                rule,
                media_identity="inode:1:2",
                last_seen_path=source / "movie.mkv",
                size_bytes=10,
                mtime_ns=123,
                stable_count=2,
            )
            service.mark_terminal(rule.rule_id, "inode:1:2", terminal_state="completed")
            session.commit()

        with sessionmaker() as session:
            state = session.query(MonitorMediaState).one()
            assert state.rule_id == rule.rule_id
            assert state.media_identity == "inode:1:2"
            assert state.size_bytes == 10
            assert state.mtime_ns == 123
            assert state.stable_count == 2
            assert state.last_enqueued_job_id == job.id
            assert state.terminal_state == "completed"
            assert state.last_seen_path.endswith("movie.mkv")
    finally:
        engine.dispose()
