from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import Job
from backend.app.services.jobs import JobService


DEFAULT_TRANSITIONS = {
    "discovered": "waiting_stable",
    "waiting_stable": "searching",
    "matched": "scraping",
    "scraping": "materializing_assets",
    "materializing_assets": "planning",
    "planning": "ready",
    "ready": "executing",
    "executing": "notifying_emby",
    "notifying_emby": "completed",
}

JobHandler = Callable[[Job], str | None]


class Worker:
    def __init__(
        self,
        sessionmaker: sessionmaker[Session],
        *,
        worker_id: str | None = None,
        handlers: dict[str, JobHandler] | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex}"
        self._handlers = handlers or {}
        self._poll_interval_seconds = poll_interval_seconds
        self._stop = asyncio.Event()

    async def run_once(self) -> bool:
        with self._sessionmaker() as session:
            service = JobService(session)
            job = service.lease_next(worker_id=self._worker_id)
            if job is None:
                session.commit()
                return False
            if job.state == "cancelled":
                service.release_lease(job)
                session.commit()
                return False
            try:
                target_state = await self._target_state(job)
                if target_state is None:
                    service.release_lease(job)
                else:
                    service.transition_job(job.id, target_state)
                    service.release_lease(job)
                session.commit()
                return True
            except Exception as exc:
                if job.state == "notifying_emby":
                    service.transition_job(
                        job.id,
                        "local_complete_emby_failed",
                        payload={
                            "error_code": exc.__class__.__name__,
                            "local_operations_complete": True,
                        },
                    )
                    service.release_lease(job)
                else:
                    service.schedule_retry(
                        job,
                        error_code=exc.__class__.__name__,
                    )
                session.commit()
                return True

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self._poll_interval_seconds)

    def stop(self) -> None:
        self._stop.set()

    async def _target_state(self, job: Job) -> str | None:
        handler = self._handlers.get(job.state)
        if handler is not None:
            result = handler(job)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return DEFAULT_TRANSITIONS.get(job.state)
