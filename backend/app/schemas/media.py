from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class MediaSidecarScanItem(BaseModel):
    path: Path
    kind: str


class MediaScanItem(BaseModel):
    path: Path
    group_key: str
    identity: str
    size_bytes: int
    mtime_ns: int
    multipart_index: int | None = None
    sidecars: list[MediaSidecarScanItem] = Field(default_factory=list)
