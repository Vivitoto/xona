from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.watch_rules import WatchRuleCreate
from backend.app.services.monitor import MonitorService
from backend.app.services.watch_rules import WatchRuleService


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def test_restart_resumes_stability_count_without_duplicate_active_jobs(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    movie = source / "movie.mkv"
    movie.write_bytes(b"movie")
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            rule = WatchRuleService(settings, session).create_rule(
                WatchRuleCreate(
                    source_directory=source,
                    destination_directory=destination,
                    stable_check_count=1,
                    stability_seconds=0,
                )
            )
            session.commit()
            rule_id = rule.rule_id

        first_monitor = MonitorService(settings, sessionmaker)
        assert first_monitor.handle_event(movie, rule_id=rule_id) == []

        restarted_monitor = MonitorService(settings, sessionmaker)
        assert [job.id for job in restarted_monitor.handle_event(movie, rule_id=rule_id)] == [1]
        assert [job.id for job in restarted_monitor.handle_event(movie, rule_id=rule_id)] == [1]

        with sessionmaker() as session:
            assert session.query(Job).count() == 1
    finally:
        engine.dispose()
