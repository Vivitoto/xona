from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.metadata import MetadataRecordData
from backend.app.schemas.source import SourceVideoDetail


class XChinaSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    normalized_query: str | None = Field(default=None, max_length=300)


class XChinaSearchCandidate(BaseModel):
    source: str = "xchina"
    source_candidate_id: str
    title: str
    image_url: str | None = None
    actors: list[str] = Field(default_factory=list)
    studio: str | None = None
    series: str | None = None
    release_date: str | None = None
    url: str


class XChinaSearchResponse(BaseModel):
    query: str
    normalized_query: str
    candidates: list[XChinaSearchCandidate] = Field(default_factory=list)


class XChinaDetailRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)
    detail: SourceVideoDetail | None = None


class XChinaDetailResponse(BaseModel):
    source_url: str
    detail: SourceVideoDetail
    metadata: MetadataRecordData
