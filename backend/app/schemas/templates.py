from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateContext(BaseModel):
    number: str | None = None
    title: str | None = None
    original_title: str | None = None
    studio: str | None = None
    series: str | None = None
    release_date: str | None = None
    actors: list[str] = Field(default_factory=list)
    source_filename: str | None = None
    xchina_id: str | None = None


class RenderedTemplate(BaseModel):
    value: str | None
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TemplatePreview(BaseModel):
    folder_path: str | None
    filename: str | None
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
