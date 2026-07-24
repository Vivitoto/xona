from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, Request
from starlette.responses import StreamingResponse

from backend.app.core.logging import recent_logs, subscribe_logs
from backend.app.schemas.logs import LogEntryRead, LogListResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = logging.getLogger(__name__)


@router.get("/recent", response_model=LogListResponse)
def recent(
    limit: int = Query(default=200, ge=1, le=1000),
    level: str | None = Query(default=None),
) -> LogListResponse:
    logger.info("Recent logs requested")
    return LogListResponse(
        entries=[LogEntryRead(**entry.model_dump()) for entry in recent_logs(limit=limit, level=level)]
    )


@router.get("/stream")
async def stream(request: Request, since_id: int | None = Query(default=None)) -> StreamingResponse:
    logger.info("Log stream opened")

    async def events():
        async for entry in subscribe_logs(since_id=since_id):
            if await request.is_disconnected():
                break
            yield f"id: {entry.id}\n"
            yield "event: log\n"
            yield f"data: {json.dumps(entry.model_dump(), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
