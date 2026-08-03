from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.schemas.operations import OrganizationMode


CoverTemplateName = Literal[
    "simple_poster",
    "jav_classic_left_strip",
    "tangxin_vlog",
]
PosterTextEffect = Literal["none", "shadow", "glow"]

PosterFontId = Literal[
    "source_han_sans",
    "noto_sans_jp",
    "noto_sans_cjk_regular",
    "noto_serif_cjk",
    "noto_serif_cjk_bold",
    "dela_gothic_one",
    "bebas_neue",
    "anton",
    "smiley_sans",
    "zcool_qingke_huangyou",
    "zcool_kuaile",
    "lxgw_wenkai",
]


class LocalVideoTechnicalInfo(BaseModel):
    path: Path
    size_bytes: int
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    format_name: str | None = None
    bit_rate: int | None = None
    fps: float | None = None


class LocalMetadataDraft(BaseModel):
    video_path: Path
    title: str
    organize_filename: str | None = None
    plot: str | None = None
    tags: list[str] = Field(default_factory=list)
    studio: str | None = None
    series: str | None = None
    release_date: str | None = None
    runtime_minutes: int | None = None
    genres: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    technical: LocalVideoTechnicalInfo | None = None


class LocalAnalyzeRequest(BaseModel):
    video_path: Path


class LocalAnalyzeResponse(BaseModel):
    video_path: Path
    cleaned_title: str
    default_organize_filename: str
    default_plot: str
    default_tags: list[str]
    default_genres: list[str]
    technical: LocalVideoTechnicalInfo
    warnings: list[str] = Field(default_factory=list)


class LocalFrameRequest(BaseModel):
    video_path: Path
    percentages: list[float] = Field(default_factory=list)
    time_points_seconds: list[float] = Field(default_factory=list)
    frame_count: int = Field(default=9, ge=1, le=36)
    duration_seconds: float | None = Field(default=None, gt=0)


class LocalCachedAsset(BaseModel):
    id: str
    kind: str
    url: str
    cache_path: Path
    content_type: str
    size_bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None
    time_seconds: float | None = None


class LocalFrameResponse(BaseModel):
    video_path: Path
    frames: list[LocalCachedAsset]
    warnings: list[str] = Field(default_factory=list)


class LocalCoverPreviewRequest(BaseModel):
    video_path: Path
    title: str
    title_angle_degrees: float = Field(default=0.0, ge=-20.0, le=20.0)
    title_position_x_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    title_position_y_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    template: CoverTemplateName = "simple_poster"
    title_font_id: PosterFontId | None = None
    title_font_size: int | None = Field(default=None, ge=16, le=180)
    title_fill_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    title_stroke_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    title_stroke_width: int | None = Field(default=None, ge=0, le=20)
    title_effect: PosterTextEffect | None = None
    selected_frame_ids: list[str] = Field(default_factory=list)
    allow_similar_frame_fallback: bool = True
    similar_frame_fallback_threshold: int = Field(default=15, ge=9, le=36)


class LocalCoverPreviewResponse(BaseModel):
    poster: LocalCachedAsset
    fanart: LocalCachedAsset
    thumb: LocalCachedAsset
    template: CoverTemplateName
    title_font_id: PosterFontId
    selected_frame_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LocalNfoPreviewRequest(BaseModel):
    metadata: LocalMetadataDraft


class LocalNfoPreviewResponse(BaseModel):
    xml_text: str
    metadata: dict[str, Any]


class LocalPlanPreviewRequest(BaseModel):
    metadata: LocalMetadataDraft
    destination_root: Path
    mode: OrganizationMode = "preview"
    folder_templates: list[str] = Field(default_factory=lambda: ["{studio}", "{title}"])
    filename_template: str = "{title}"
    poster_ref: str | None = None
    fanart_ref: str | None = None
    thumb_ref: str | None = None
    selected_frame_ids: list[str] = Field(default_factory=list)
    extra_backdrop_count: int = Field(default=0, ge=0, le=10)


class LocalPlanPreviewResponse(BaseModel):
    plan_id: str
    metadata: dict[str, Any]
    materialized_assets: list[dict[str, Any]] = Field(default_factory=list)
    nfo_xml: str
    plan: dict[str, Any]


class LocalExecutePlanRequest(BaseModel):
    approved: bool
    plan_version: int = 1


class LocalExecutePlanResponse(BaseModel):
    plan_id: str
    job_id: int | None = None
    state: str


class LocalCacheCleanupRequest(BaseModel):
    plan_version: int = 1


class LocalCacheCleanupResponse(BaseModel):
    plan_id: str
    deleted_directories: int
    deleted_files: int
    cache_dirs: list[Path] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LocalScanRequest(BaseModel):
    directory: Path
    recursive: bool = True
    ignore_patterns: list[str] = Field(default_factory=list)


class LocalScannedVideo(BaseModel):
    path: Path
    filename: str
    cleaned_title: str
    default_organize_filename: str
    size_bytes: int
    mtime_ns: int
    group_key: str
    multipart_index: int | None = None


class LocalScanResponse(BaseModel):
    scanned_count: int
    videos: list[LocalScannedVideo]


LocalMetadataBatchStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "cancelled",
    "failed",
]
LocalMetadataBatchItemStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "executing",
    "executed",
    "execute_failed",
    "cancelled",
]
LocalMetadataBatchLogTone = Literal[
    "active",
    "success",
    "warning",
    "danger",
    "neutral",
]


class LocalBatchCoverSettings(BaseModel):
    template: CoverTemplateName = "simple_poster"
    title_font_id: PosterFontId | None = None
    title_font_size: int | None = Field(default=None, ge=16, le=180)
    title_fill_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    title_stroke_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    title_stroke_width: int | None = Field(default=None, ge=0, le=20)
    title_effect: PosterTextEffect | None = None
    title_angle_degrees: float = Field(default=0.0, ge=-20.0, le=20.0)
    title_position_x_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    title_position_y_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    allow_similar_frame_fallback: bool = True
    similar_frame_fallback_threshold: int = Field(default=15, ge=9, le=36)


class LocalMetadataBatchOptions(BaseModel):
    destination_root: Path
    mode: OrganizationMode = "preview"
    folder_templates: list[str] = Field(default_factory=lambda: ["{studio}", "{title}"])
    filename_template: str = "{title}"
    extra_backdrop_count: int = Field(default=0, ge=0, le=10)
    frame_count: int = Field(default=9, ge=1, le=36)
    concurrency: int = Field(default=2, ge=1, le=4)
    cleanup_cache_after_execute: bool = True


class LocalMetadataBatchCreateItem(BaseModel):
    video_path: Path
    filename: str | None = None
    metadata: LocalMetadataDraft
    cover_settings: LocalBatchCoverSettings


class LocalMetadataBatchCreateRequest(BaseModel):
    options: LocalMetadataBatchOptions
    items: list[LocalMetadataBatchCreateItem] = Field(min_length=1, max_length=1000)


class LocalMetadataBatchLogEntry(BaseModel):
    tone: LocalMetadataBatchLogTone
    message: str
    created_at: datetime


class LocalMetadataBatchItemRead(BaseModel):
    item_id: int
    video_path: Path
    filename: str
    draft: LocalMetadataDraft
    cover_settings: LocalBatchCoverSettings
    status: LocalMetadataBatchItemStatus
    error: str | None = None
    logs: list[LocalMetadataBatchLogEntry] = Field(default_factory=list)
    frames: list[LocalCachedAsset] = Field(default_factory=list)
    selected_frame_ids: list[str] = Field(default_factory=list)
    cover_preview: LocalCoverPreviewResponse | None = None
    plan_id: str | None = None
    plan_preview: LocalPlanPreviewResponse | None = None
    execute_result: LocalExecutePlanResponse | None = None
    created_at: datetime
    updated_at: datetime


class LocalMetadataBatchSummary(BaseModel):
    batch_id: str
    status: LocalMetadataBatchStatus
    options: LocalMetadataBatchOptions
    total_count: int
    pending_count: int
    running_count: int
    succeeded_count: int
    failed_count: int
    executable_count: int
    executed_count: int
    execute_failed_count: int
    created_at: datetime
    updated_at: datetime


class LocalMetadataBatchRead(LocalMetadataBatchSummary):
    items: list[LocalMetadataBatchItemRead] = Field(default_factory=list)


class LocalMetadataBatchListResponse(BaseModel):
    batches: list[LocalMetadataBatchSummary]
