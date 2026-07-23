from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedName(BaseModel):
    original: str
    search_text: str
    identifier: str | None = None
    parent_hint: str | None = None
    site_prefix: str | None = None
    release_suffix: str | None = None
    multipart_index: int | None = None
    technical_tokens: list[str] = Field(default_factory=list)
