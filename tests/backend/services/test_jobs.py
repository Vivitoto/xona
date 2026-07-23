from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job, JobEvent
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.jobs import JobService, InvalidJobTransition


def _database(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return engine, get_sessionmaker(engine)


def test_valid_transitions_write_redacted_events_and_invalid_transitions_fail(
    tmp_path: Path,
) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            service = JobService(session)
            job = service.create_job(
                media_identity="inode:1:2",
                rule_id="rule-1",
                payload={"source_url": "https://example.test/?api_key=secret"},
            )

            service.transition_job(
                job.id,
                "waiting_stable",
                payload={"cookie": "session=secret", "note": "ok"},
            )
            with pytest.raises(InvalidJobTransition):
                service.transition_job(job.id, "completed")
            session.commit()

            loaded = session.get(Job, job.id)
            assert loaded is not None
            assert loaded.state == "waiting_stable"
            events = session.query(JobEvent).order_by(JobEvent.id).all()
            assert [(event.from_state, event.to_state) for event in events] == [
                (None, "discovered"),
                ("discovered", "waiting_stable"),
            ]
            assert events[1].payload["cookie"] == "********"
            assert "secret" not in str(events[1].payload)
    finally:
        engine.dispose()


def test_active_job_uniqueness_and_retry_and_cancel(tmp_path: Path) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            service = JobService(session)
            job = service.create_job(media_identity="media-a", rule_id="rule-1")
            with pytest.raises(ValueError):
                service.create_job(media_identity="media-a", rule_id="rule-1")
            manual = service.create_job(media_identity="media-a", manual=True)
            with pytest.raises(ValueError):
                service.create_job(media_identity="media-a", manual=True)

            service.schedule_retry(job, error_code="network_timeout", base_delay_seconds=10)
            assert job.attempts == 1
            first_next_run = job.next_run_at
            service.schedule_retry(job, error_code="network_timeout", base_delay_seconds=10)
            assert job.attempts == 2
            assert job.next_run_at > first_next_run

            service.cancel_job(manual.id, payload={"api_key": "secret"})
            assert manual.state == "cancelled"
            assert session.query(JobEvent).filter_by(job_id=manual.id).all()[-1].to_state == "cancelled"
    finally:
        engine.dispose()
