from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field


class MetadataActor(BaseModel):
    name: str
    role: str | None = None
    source_id: str | None = None
    profile_url: str | None = None
    portrait_url: str | None = None
    portrait_reference: str | None = None


class MetadataAssets(BaseModel):
    poster_url: str | None = None
    fanart_url: str | None = None
    backdrop_urls: list[str] = Field(default_factory=list)
    thumb_url: str | None = None
    clearlogo_url: str | None = None
    trailer_url: str | None = None


class MetadataRecordData(BaseModel):
    source: str
    xchina_id: str | None = None
    source_url: str
    title: str
    original_title: str | None = None
    sort_title: str | None = None
    plot: str | None = None
    outline: str | None = None
    release_date: str | None = None
    runtime_minutes: int | None = None
    studio: str | None = None
    series: str | None = None
    director: str | None = None
    actors: list[MetadataActor] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    assets: MetadataAssets = Field(default_factory=MetadataAssets)

    @property
    def source_id(self) -> str:
        if self.xchina_id:
            return self.xchina_id
        digest = hashlib.sha256()
        digest.update(self.source.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.source_url.encode("utf-8"))
        return f"{self.source}-{digest.hexdigest()[:16]}"
