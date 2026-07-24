from __future__ import annotations

from pydantic import BaseModel, Field


class LogEntryRead(BaseModel):
    id: int
    timestamp: str
    level: str
    logger: str
    message: str
    source: str = "application"


class LogListResponse(BaseModel):
    entries: list[LogEntryRead] = Field(default_factory=list)
    docker_logs_note: str = (
        "Xona application logs are written to stdout, so they are visible with docker logs."
    )
