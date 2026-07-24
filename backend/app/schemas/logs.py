from __future__ import annotations

from pydantic import BaseModel, Field


class LogEntryRead(BaseModel):
    id: int
    timestamp: str
    level: str
    logger: str
    component: str
    message: str
    source: str = "application"


class LogListResponse(BaseModel):
    entries: list[LogEntryRead] = Field(default_factory=list)
    docker_logs_note: str = (
        "Docker logs use: time | level | component | message. View them with docker logs -f xona."
    )
