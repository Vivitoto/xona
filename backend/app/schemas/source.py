from __future__ import annotations

from pydantic import BaseModel, Field


class SourceAsset(BaseModel):
    url: str
    kind: str


class SourceActorRef(BaseModel):
    name: str
    source_id: str | None = None
    profile_url: str | None = None
    portrait_url: str | None = None


class SourceSearchResult(BaseModel):
    source: str = "xchina"
    source_candidate_id: str
    title: str
    url: str
    release_date: str | None = None
    thumbnail_url: str | None = None
    actors: list[SourceActorRef] = Field(default_factory=list)
    studio: str | None = None
    series: str | None = None


class SourceVideoDetail(BaseModel):
    source: str = "xchina"
    source_id: str
    source_url: str
    title: str
    original_title: str | None = None
    plot: str | None = None
    release_date: str | None = None
    runtime_minutes: int | None = None
    studio: str | None = None
    series: str | None = None
    director: str | None = None
    actors: list[SourceActorRef] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    poster: SourceAsset | None = None
    fanart: SourceAsset | None = None
    backdrops: list[SourceAsset] = Field(default_factory=list)
    trailer: SourceAsset | None = None
    source_snapshot_eligible: bool = False
    is_complete: bool = False
    completeness_flags: list[str] = Field(default_factory=list)


class SourceActorDetail(BaseModel):
    source: str = "xchina"
    source_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    profile_url: str
    portrait_url: str | None = None
    biography: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    associated_works: list[dict[str, str]] = Field(default_factory=list)
    placeholder_image: bool = False
