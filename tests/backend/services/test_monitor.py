from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job, MonitorMediaState
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.watch_rules import WatchRuleCreate
from backend.app.services.monitor import MonitorService
from backend.app.services.watch_rules import WatchRuleService


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def _create_rule(tmp_path: Path, *, realtime: bool = True):
    root = tmp_path / "media"
    source = root / "incoming"
    destination = source / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    settings, engine, sessionmaker = _database(tmp_path, root)
    with sessionmaker() as session:
        rule = WatchRuleService(settings, session).create_rule(
            WatchRuleCreate(
                source_directory=source,
                destination_directory=destination,
                realtime=realtime,
                include_patterns=["*.mkv"],
                stable_check_count=1,
                stability_seconds=0,
            )
        )
        session.commit()
        rule_id = rule.rule_id
    return settings, engine, sessionmaker, rule_id, source, destination


def test_monitor_events_update_state_and_enqueue_once_when_stable(tmp_path: Path) -> None:
    settings, engine, sessionmaker, rule_id, source, destination = _create_rule(tmp_path)
    movie = source / "movie.mkv"
    movie.write_bytes(b"movie")
    try:
        monitor = MonitorService(settings, sessionmaker)
        first = monitor.handle_event(movie, rule_id=rule_id)
        second = monitor.handle_event(movie, rule_id=rule_id)
        third = monitor.handle_event(movie, rule_id=rule_id)

        assert first == []
        assert [job.id for job in second] == [1]
        assert [job.id for job in third] == [1]
        with sessionmaker() as session:
            assert session.query(Job).count() == 1
            state = session.query(MonitorMediaState).one()
            assert state.stable_count >= 1
            assert state.last_enqueued_job_id == 1
    finally:
        engine.dispose()


def test_monitor_applies_include_exclude_and_destination_prefixes_before_enqueue(
    tmp_path: Path,
) -> None:
    settings, engine, sessionmaker, rule_id, source, destination = _create_rule(tmp_path)
    ignored_extension = source / "movie.txt"
    ignored_extension.write_text("not media", encoding="utf-8")
    loop_path = destination / "movie.mkv"
    loop_path.write_bytes(b"loop")
    try:
        monitor = MonitorService(settings, sessionmaker)
        assert monitor.handle_event(ignored_extension, rule_id=rule_id) == []
        assert monitor.handle_event(loop_path, rule_id=rule_id) == []
        with sessionmaker() as session:
            assert session.query(Job).count() == 0
    finally:
        engine.dispose()


def test_monitor_start_falls_back_to_polling_and_reload_keeps_jobs(tmp_path: Path) -> None:
    settings, engine, sessionmaker, rule_id, source, destination = _create_rule(
        tmp_path,
        realtime=True,
    )
    movie = source / "movie.mkv"
    movie.write_bytes(b"movie")

    def failing_observer_factory(_monitor: MonitorService):
        raise RuntimeError("watchdog unavailable")

    try:
        monitor = MonitorService(
            settings,
            sessionmaker,
            observer_factory=failing_observer_factory,
        )
        monitor.start()
        monitor.handle_event(movie, rule_id=rule_id)
        monitor.handle_event(movie, rule_id=rule_id)
        monitor.reload_rules()

        assert monitor.realtime_available is False
        assert rule_id in monitor.polling_rule_ids
        assert rule_id in monitor.active_rule_ids
        with sessionmaker() as session:
            assert session.query(Job).count() == 1
    finally:
        monitor.stop()
        engine.dispose()
