from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app
from backend.app.services.jobs import JobService


ORIGIN = "http://testserver"


def test_jobs_api_lists_details_events_retry_and_cancel(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                service = JobService(session)
                review = service.create_job(
                    media_identity="media-review",
                    state="review_required",
                    manual=True,
                    payload={
                        "api_key": "secret",
                        "manual": {"gate_reasons": ["threshold_not_met"]},
                    },
                )
                cancel = service.create_job(media_identity="media-cancel")
                session.commit()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return {
                    "list": await client.get("/api/jobs?state=review_required"),
                    "detail": await client.get(f"/api/jobs/{review.id}"),
                    "events": await client.get(f"/api/jobs/{review.id}/events"),
                    "retry": await client.post(
                        f"/api/jobs/{review.id}/retry",
                        headers={"Origin": ORIGIN},
                    ),
                    "cancel": await client.post(
                        f"/api/jobs/{cancel.id}/cancel",
                        headers={"Origin": ORIGIN},
                    ),
                }

    responses = asyncio.run(run())

    assert responses["list"].json()["jobs"][0]["state"] == "review_required"
    assert responses["list"].json()["jobs"][0]["gate_reasons"] == ["threshold_not_met"]
    assert "secret" not in responses["detail"].text
    assert responses["events"].json()["events"][0]["payload"]["api_key"] == "********"
    assert responses["retry"].json()["job"]["state"] == "searching"
    assert responses["cancel"].json()["job"]["state"] == "cancelled"
