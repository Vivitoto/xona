from __future__ import annotations

import hashlib
import logging
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.schemas.assets import MaterializedAsset
from backend.app.schemas.local_metadata import (
    LocalAnalyzeRequest,
    LocalAnalyzeResponse,
    LocalCacheCleanupResponse,
    LocalCachedAsset,
    LocalCoverPreviewRequest,
    LocalCoverPreviewResponse,
    LocalExecutePlanResponse,
    LocalFrameRequest,
    LocalFrameResponse,
    LocalMetadataDraft,
    LocalNfoPreviewResponse,
    LocalPlanPreviewRequest,
    LocalPlanPreviewResponse,
    LocalScanRequest,
    LocalScanResponse,
    LocalScannedVideo,
    LocalVideoTechnicalInfo,
)
from backend.app.schemas.media import MediaScanItem
from backend.app.schemas.metadata import (
    MetadataActor,
    MetadataAssets,
    MetadataRecordData,
    MetadataTechnicalInfo,
)
from backend.app.schemas.operations import GeneratedArtifact, OperationPlan
from backend.app.schemas.templates import TemplateContext
from backend.app.services import scanner
from backend.app.services.cover_templates import CoverTemplateError, generate_cover_previews
from backend.app.services.nfo import movie_nfo_relative_path, render_movie_nfo
from backend.app.services.operation_executor import (
    OperationExecutionError,
    OperationExecutor,
    OperationJournal,
)
from backend.app.services.normalization import normalize_filename_for_search, sanitize_path_component
from backend.app.services.organizer_plans import (
    OperationPlanConflictError,
    OperationPlanSafetyError,
    OrganizerPlanService,
)
from backend.app.services.storage_roots import (
    StorageRootService,
    StorageRootValidationError,
)
from backend.app.services.templates import preview_template
from backend.app.services.video_probe import (
    MediaToolExecutionError,
    MediaToolUnavailableError,
    extract_video_frames,
    probe_video,
)


DEFAULT_LOCAL_METADATA_VALUES: tuple[str, ...] = ("{actors}", "{studio}", "{resolution}")
DEFAULT_LOCAL_TAGS: tuple[str, ...] = DEFAULT_LOCAL_METADATA_VALUES
DEFAULT_LOCAL_GENRES: tuple[str, ...] = DEFAULT_LOCAL_METADATA_VALUES
STUDIO_TAG_PREFIX = "片商: "
MAX_EXTRA_BACKDROP_COUNT = 10
logger = logging.getLogger(__name__)


class LocalMetadataError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int = 400,
        reasons: list[str] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.reasons = reasons or [code]


class LocalMetadataService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session
        self._storage_roots = StorageRootService(settings, session)

    def scan(self, payload: LocalScanRequest) -> LocalScanResponse:
        try:
            self._storage_roots.validate_inside_root(payload.directory)
            items = scanner.scan_directory(
                payload.directory,
                recursive=payload.recursive,
                ignore_patterns=tuple(payload.ignore_patterns),
                storage_roots=self._storage_roots,
            )
        except (StorageRootValidationError, ValueError) as exc:
            raise LocalMetadataError("scan_failed", reasons=[str(exc)]) from exc

        return LocalScanResponse(
            scanned_count=len(items),
            videos=[
                LocalScannedVideo(
                    path=item.path,
                    filename=item.path.name,
                    cleaned_title=clean_local_title(item.path),
                    default_organize_filename=clean_local_title(item.path),
                    size_bytes=item.size_bytes,
                    mtime_ns=item.mtime_ns,
                    group_key=item.group_key,
                    multipart_index=item.multipart_index,
                )
                for item in items
            ],
        )

    def analyze(self, payload: LocalAnalyzeRequest) -> LocalAnalyzeResponse:
        path = self._validate_video_path(payload.video_path)
        try:
            technical = probe_video(path)
        except (MediaToolUnavailableError, MediaToolExecutionError) as exc:
            raise _tool_error(exc) from exc

        title = clean_local_title(path)
        return LocalAnalyzeResponse(
            video_path=path,
            cleaned_title=title,
            default_organize_filename=title,
            default_plot=title,
            default_tags=list(DEFAULT_LOCAL_TAGS),
            default_genres=list(DEFAULT_LOCAL_GENRES),
            technical=technical,
        )

    def generate_frames(self, payload: LocalFrameRequest) -> LocalFrameResponse:
        path = self._validate_video_path(payload.video_path)
        warnings: list[str] = []
        try:
            times = _requested_times(payload)
            if not times:
                technical = probe_video(path)
                if technical.duration_seconds is None:
                    warnings.append("duration_unavailable")
                    times = _fallback_times(payload.frame_count)
                else:
                    times = _percentage_times(
                        payload.percentages,
                        technical.duration_seconds,
                        frame_count=payload.frame_count,
                    )
            frame_dir = self._cache_dir_for_video(path) / "frames"
            generated = extract_video_frames(path, output_dir=frame_dir, times_seconds=times)
        except (MediaToolUnavailableError, MediaToolExecutionError) as exc:
            raise _tool_error(exc) from exc

        return LocalFrameResponse(
            video_path=path,
            frames=[
                self._cache_asset(frame_path, kind="frame", time_seconds=time_seconds)
                for frame_path, time_seconds in generated
            ],
            warnings=warnings,
        )

    def cover_preview(
        self,
        payload: LocalCoverPreviewRequest,
    ) -> LocalCoverPreviewResponse:
        self._validate_video_path(payload.video_path)
        frame_paths = [self.cache_path_for_ref(ref) for ref in payload.selected_frame_ids]
        if not frame_paths:
            frame_paths = sorted((self._cache_dir_for_video(payload.video_path) / "frames").glob("*.jpg"))
        if not frame_paths:
            raise LocalMetadataError("frame_required", reasons=["Generate frames before cover preview"])

        try:
            generated = generate_cover_previews(
                title=payload.title,
                title_angle_degrees=payload.title_angle_degrees,
                title_position_x_percent=payload.title_position_x_percent,
                title_position_y_percent=payload.title_position_y_percent,
                template=payload.template,
                title_font_id=payload.title_font_id,
                title_font_size=payload.title_font_size,
                title_fill_color=payload.title_fill_color,
                title_stroke_color=payload.title_stroke_color,
                title_stroke_width=payload.title_stroke_width,
                title_effect=payload.title_effect,
                frame_paths=frame_paths,
                output_dir=self._cache_dir_for_video(payload.video_path) / "covers",
            )
        except CoverTemplateError as exc:
            raise LocalMetadataError("cover_generation_failed", reasons=[str(exc)]) from exc

        return LocalCoverPreviewResponse(
            poster=self._cache_asset(generated.poster_path, kind="poster"),
            fanart=self._cache_asset(generated.fanart_path, kind="fanart"),
            thumb=self._cache_asset(generated.thumb_path, kind="thumb"),
            template=payload.template,
            title_font_id=generated.title_font_id,
            selected_frame_ids=list(payload.selected_frame_ids),
        )

    def nfo_preview(self, metadata: LocalMetadataDraft) -> LocalNfoPreviewResponse:
        record = local_metadata_record(metadata)
        xml_text = render_movie_nfo(record).decode("utf-8")
        return LocalNfoPreviewResponse(
            xml_text=xml_text,
            metadata=record.model_dump(mode="json"),
        )

    def preview_plan(
        self,
        payload: LocalPlanPreviewRequest,
    ) -> LocalPlanPreviewResponse:
        path = self._validate_video_path(payload.metadata.video_path)
        record = local_metadata_record(payload.metadata)
        media_item = _media_item_for_path(path)
        organize_filename = clean_organize_filename(
            payload.metadata.organize_filename,
            source_suffix=path.suffix,
        )
        template = preview_template(
            folder_templates=payload.folder_templates,
            filename_template="{title}" if organize_filename is not None else payload.filename_template,
            context=_template_context(record, media_item),
        )
        if organize_filename is not None:
            template = template.model_copy(
                update={"filename": f"{organize_filename}{path.suffix}"}
            )
        nfo_xml = render_movie_nfo(record).decode("utf-8")
        generated: list[GeneratedArtifact] = []
        if template.filename:
            generated.append(
                GeneratedArtifact(
                    relative_path=movie_nfo_relative_path(template.filename),
                    artifact_type="nfo",
                    content_text=nfo_xml,
                    allow_replace_existing=False,
                )
            )

        materialized = self._plan_assets(
            video_path=path,
            destination_root=payload.destination_root,
            poster_ref=payload.poster_ref,
            fanart_ref=payload.fanart_ref,
            thumb_ref=payload.thumb_ref,
            selected_frame_ids=payload.selected_frame_ids,
            extra_backdrop_count=payload.extra_backdrop_count,
        )
        try:
            plan = OrganizerPlanService(self._session, self._storage_roots).create_plan(
                mode=payload.mode,
                media_items=[media_item],
                destination_root=payload.destination_root,
                template_preview=template,
                materialized_assets=materialized,
                generated_artifacts=generated,
                job_id=None,
            )
        except OperationPlanConflictError as exc:
            raise LocalMetadataError(
                "destination_collision",
                status_code=409,
                reasons=[conflict.reason for conflict in exc.conflicts],
            ) from exc
        except OperationPlanSafetyError as exc:
            raise LocalMetadataError("plan_rejected", reasons=[str(exc)]) from exc

        return LocalPlanPreviewResponse(
            plan_id=plan.plan_id,
            metadata=record.model_dump(mode="json"),
            materialized_assets=[asset.model_dump(mode="json") for asset in materialized],
            nfo_xml=nfo_xml,
            plan=plan.snapshot_json(),
        )

    def execute_plan(
        self,
        plan_id: str,
        *,
        approved: bool,
        plan_version: int,
    ) -> LocalExecutePlanResponse:
        if not approved:
            raise LocalMetadataError("plan_approval_required")
        row = self._session.scalar(
            select(OperationPlanModel).where(OperationPlanModel.plan_id == plan_id)
        )
        if row is None:
            raise LocalMetadataError("plan_not_found", status_code=404)
        if row.job_id is not None:
            raise LocalMetadataError("plan_not_found", status_code=404)
        if int(row.version) != plan_version:
            raise LocalMetadataError("plan_version_mismatch")
        if row.status not in {"approved", "planned"}:
            raise LocalMetadataError(f"plan_not_executable:{row.status}")
        plan = OperationPlan.model_validate(row.plan_json).model_copy(
            update={"database_id": row.id}
        )
        if plan.mode == "preview":
            raise LocalMetadataError("plan_not_executable:preview_mode")
        try:
            OperationExecutor(
                self._storage_roots,
                journal=OperationJournal(self._session),
            ).execute(plan)
        except OperationExecutionError as exc:
            row.status = "failed"
            self._session.flush()
            raise LocalMetadataError(exc.error_code, status_code=409) from exc
        row.status = "completed"
        self._session.flush()
        return LocalExecutePlanResponse(
            plan_id=plan_id,
            job_id=row.job_id,
            state=row.status,
        )

    def cleanup_plan_cache(
        self,
        plan_id: str,
        *,
        plan_version: int,
    ) -> LocalCacheCleanupResponse:
        row = self._session.scalar(
            select(OperationPlanModel).where(OperationPlanModel.plan_id == plan_id)
        )
        if row is None:
            raise LocalMetadataError("plan_not_found", status_code=404)
        if row.job_id is not None:
            raise LocalMetadataError("plan_not_found", status_code=404)
        if int(row.version) != plan_version:
            raise LocalMetadataError("plan_version_mismatch")
        if row.status != "completed":
            raise LocalMetadataError("plan_not_completed", status_code=409)

        plan = OperationPlan.model_validate(row.plan_json)
        cache_dirs = self._local_metadata_cache_dirs_for_plan(plan)
        deleted_directories = 0
        deleted_files = 0
        warnings: list[str] = []

        for cache_dir in cache_dirs:
            if not cache_dir.exists():
                warnings.append(f"cache_dir_missing:{cache_dir}")
                logger.info(
                    "Local metadata cache cleanup skipped missing directory plan_id=%s cache_dir=%s",
                    plan_id,
                    cache_dir,
                )
                continue
            if not cache_dir.is_dir():
                warnings.append(f"cache_dir_not_directory:{cache_dir}")
                logger.warning(
                    "Local metadata cache cleanup skipped non-directory plan_id=%s cache_dir=%s",
                    plan_id,
                    cache_dir,
                )
                continue

            file_count = sum(1 for item in cache_dir.rglob("*") if item.is_file())
            shutil.rmtree(cache_dir)
            deleted_directories += 1
            deleted_files += file_count
            logger.info(
                "Local metadata cache directory removed plan_id=%s cache_dir=%s files=%s",
                plan_id,
                cache_dir,
                file_count,
            )

        if not cache_dirs:
            logger.info(
                "Local metadata cache cleanup found no per-video cache directories plan_id=%s",
                plan_id,
            )

        return LocalCacheCleanupResponse(
            plan_id=plan_id,
            deleted_directories=deleted_directories,
            deleted_files=deleted_files,
            cache_dirs=list(cache_dirs),
            warnings=warnings,
        )

    def cache_path_for_ref(self, ref: str) -> Path:
        relative = Path(ref)
        if relative.is_absolute() or any(part == ".." for part in relative.parts):
            raise LocalMetadataError("invalid_cache_ref")
        root = self._cache_root().resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise LocalMetadataError("invalid_cache_ref") from exc
        if not candidate.is_file():
            raise LocalMetadataError("cache_ref_not_found", status_code=404)
        return candidate

    def _validate_video_path(self, video_path: Path | str) -> Path:
        path = Path(video_path)
        try:
            validation = self._storage_roots.validate_inside_root(path)
        except StorageRootValidationError as exc:
            raise LocalMetadataError("path_outside_storage_root", reasons=[str(exc)]) from exc
        if not validation.path.is_file():
            raise LocalMetadataError("video_not_found", status_code=404)
        return validation.path

    def _cache_root(self) -> Path:
        return self._settings.config_dir / "cache" / "local_metadata"

    def _cache_dir_for_video(self, video_path: Path | str) -> Path:
        path = Path(video_path)
        stat = path.stat()
        digest = hashlib.sha256()
        digest.update(str(path).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        key = digest.hexdigest()
        return self._cache_root() / key[:2] / key

    def _cache_asset(
        self,
        path: Path,
        *,
        kind: str,
        time_seconds: float | None = None,
    ) -> LocalCachedAsset:
        relative = path.resolve().relative_to(self._cache_root().resolve())
        image_width, image_height = _image_size(path)
        return LocalCachedAsset(
            id=relative.as_posix(),
            kind=kind,
            url=f"/api/local-metadata/cache/{quote(relative.as_posix(), safe='/')}",
            cache_path=path,
            content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            size_bytes=path.stat().st_size,
            sha256=_hash_file(path),
            width=image_width,
            height=image_height,
            time_seconds=time_seconds,
        )

    def _local_metadata_cache_dirs_for_plan(
        self,
        plan: OperationPlan,
    ) -> tuple[Path, ...]:
        root = self._cache_root().resolve(strict=False)
        cache_dirs: list[Path] = []
        for cache_path in plan.materialized_asset_cache_paths:
            cache_dir = _video_cache_dir_for_asset_path(cache_path, root=root)
            if cache_dir is not None:
                cache_dirs.append(cache_dir)
        return tuple(dict.fromkeys(cache_dirs))

    def _plan_assets(
        self,
        *,
        video_path: Path,
        destination_root: Path,
        poster_ref: str | None,
        fanart_ref: str | None,
        thumb_ref: str | None,
        selected_frame_ids: list[str],
        extra_backdrop_count: int,
    ) -> list[MaterializedAsset]:
        assets: list[MaterializedAsset] = []
        if poster_ref:
            assets.append(
                self._plan_asset_from_cache(
                    poster_ref,
                    destination_root=destination_root,
                    kind="poster",
                    relative_path="poster.jpg",
                )
            )
        if fanart_ref:
            assets.append(
                self._plan_asset_from_cache(
                    fanart_ref,
                    destination_root=destination_root,
                    kind="fanart",
                    relative_path="fanart.jpg",
                )
            )
        if thumb_ref:
            assets.append(
                self._plan_asset_from_cache(
                    thumb_ref,
                    destination_root=destination_root,
                    kind="thumb",
                    relative_path="thumb.jpg",
                )
            )
        for index, frame_ref in enumerate(
            self._selected_backdrop_refs(
                video_path=video_path,
                selected_frame_ids=selected_frame_ids,
                count=extra_backdrop_count,
            ),
            start=1,
        ):
            assets.append(
                self._plan_asset_from_cache(
                    frame_ref,
                    destination_root=destination_root,
                    kind="backdrop",
                    relative_path=_backdrop_relative_path(index),
                )
            )
        return assets

    def _selected_backdrop_refs(
        self,
        *,
        video_path: Path,
        selected_frame_ids: list[str],
        count: int,
    ) -> list[str]:
        if count <= 0:
            return []
        count = min(count, MAX_EXTRA_BACKDROP_COUNT)
        refs = list(selected_frame_ids)
        if not refs:
            cache_root = self._cache_root().resolve()
            refs = [
                frame.resolve().relative_to(cache_root).as_posix()
                for frame in sorted((self._cache_dir_for_video(video_path) / "frames").glob("*.jpg"))
            ]
        refs = list(dict.fromkeys(refs))
        if not refs:
            raise LocalMetadataError(
                "frame_required",
                reasons=["Generate frames before requesting extra backdrop outputs"],
            )
        return refs[:count]

    def _plan_asset_from_cache(
        self,
        ref: str,
        *,
        destination_root: Path,
        kind: str,
        relative_path: str,
    ) -> MaterializedAsset:
        source = self.cache_path_for_ref(ref)
        try:
            self._storage_roots.validate_inside_root(destination_root)
        except StorageRootValidationError as exc:
            raise LocalMetadataError("destination_outside_storage_root", reasons=[str(exc)]) from exc
        digest = _hash_file(source)
        cache_path = source
        return MaterializedAsset(
            kind=kind,
            relative_path=relative_path,
            source_url=f"local-metadata-cache:{ref}",
            cache_path=cache_path,
            content_type=mimetypes.guess_type(source.name)[0] or "image/jpeg",
            size_bytes=source.stat().st_size,
            sha256=digest,
        )


def _video_cache_dir_for_asset_path(path: Path, *, root: Path) -> Path | None:
    candidate = Path(path).resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return None

    parts = relative.parts
    if len(parts) < 3:
        return None
    prefix, key = parts[0], parts[1]
    if not _looks_like_video_cache_key(prefix, key):
        return None

    cache_dir = (root / prefix / key).resolve(strict=False)
    try:
        cache_dir.relative_to(root)
    except ValueError:
        return None
    if cache_dir == root:
        return None
    return cache_dir


def _looks_like_video_cache_key(prefix: str, key: str) -> bool:
    return (
        len(prefix) == 2
        and len(key) == 64
        and key.startswith(prefix)
        and all(character in "0123456789abcdef" for character in key.lower())
    )


def clean_local_title(video_path: Path | str) -> str:
    normalized = normalize_filename_for_search(
        Path(video_path).name,
        preserve_underscores=True,
    )
    if normalized.search_text:
        return normalized.search_text
    stem = Path(video_path).stem.replace("_", " ").replace(".", " ").replace("-", " ")
    fallback = " ".join(stem.split()).strip()
    return fallback or "Untitled"


def clean_organize_filename(value: str | None, *, source_suffix: str = "") -> str | None:
    if value is None:
        return None
    raw = " ".join(value.split()).strip()
    if not raw:
        return None
    cleaned = sanitize_path_component(raw)
    if source_suffix and cleaned.lower().endswith(source_suffix.lower()):
        cleaned = cleaned[: -len(source_suffix)].strip(" .")
    return cleaned or None


def _backdrop_relative_path(index: int) -> str:
    return "backdrop.jpg" if index == 1 else f"backdrop{index - 1}.jpg"


def local_metadata_record(draft: LocalMetadataDraft) -> MetadataRecordData:
    title = " ".join(draft.title.split()).strip() or clean_local_title(draft.video_path)
    plot = _clean_text(draft.plot)
    actors = _clean_list(draft.actors)
    studio = _clean_text(draft.studio)
    technical = _metadata_technical_info(draft.technical)
    tags = _expand_local_metadata_values(
        draft.tags,
        technical=technical,
        actors=actors,
        studio=studio,
    )
    genres = _expand_local_metadata_values(
        draft.genres,
        technical=technical,
        actors=actors,
        studio=studio,
    )
    return MetadataRecordData(
        source="local",
        xchina_id=None,
        source_url=f"file://{draft.video_path}",
        title=title,
        original_title=None,
        sort_title=title,
        plot=plot,
        outline=plot,
        release_date=_clean_text(draft.release_date),
        runtime_minutes=draft.runtime_minutes,
        studio=studio,
        series=_clean_text(draft.series),
        actors=[MetadataActor(name=name) for name in actors],
        genres=genres,
        tags=tags,
        labels=_local_labels(technical=technical, actors=actors, studio=studio),
        assets=MetadataAssets(),
        technical=technical,
    )


def _metadata_technical_info(
    technical: LocalVideoTechnicalInfo | None,
) -> MetadataTechnicalInfo | None:
    if technical is None:
        return None
    return MetadataTechnicalInfo(
        duration_seconds=technical.duration_seconds,
        width=technical.width,
        height=technical.height,
        video_codec=technical.video_codec,
        audio_codec=technical.audio_codec,
        bit_rate=technical.bit_rate,
        fps=technical.fps,
    )


def _local_labels(
    *,
    technical: MetadataTechnicalInfo | None,
    actors: list[str],
    studio: str | None,
) -> list[str]:
    labels: list[str] = []
    resolution = _resolution_label(technical)
    if resolution:
        labels.append(resolution)
    labels.extend(actors)
    if studio:
        labels.append(studio)
    return _clean_list(labels)


def _expand_local_metadata_values(
    values: list[str],
    *,
    technical: MetadataTechnicalInfo | None,
    actors: list[str],
    studio: str | None,
) -> list[str]:
    resolution = _resolution_label(technical)
    expanded: list[str] = []
    for raw_value in values:
        value = " ".join(raw_value.split()).strip()
        if not value:
            continue
        if value == "{actors}":
            expanded.extend(actors)
            continue
        if value == "{studio}":
            if studio:
                expanded.append(f"{STUDIO_TAG_PREFIX}{studio}")
            continue
        if value == "{resolution}":
            if resolution:
                expanded.append(resolution)
            continue

        rendered = value
        rendered = rendered.replace("{actors}", ", ".join(actors))
        rendered = rendered.replace("{first_actor}", actors[0] if actors else "")
        rendered = rendered.replace(
            "{studio}",
            f"{STUDIO_TAG_PREFIX}{studio}" if studio else "",
        )
        rendered = rendered.replace("{resolution}", resolution or "")
        expanded.append(rendered)
    return _clean_list(expanded)


def _resolution_label(technical: MetadataTechnicalInfo | None) -> str | None:
    if technical is None:
        return None
    width = technical.width or 0
    height = technical.height or 0
    if width >= 3840 or height >= 2160:
        return "4K"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    if height > 0:
        return f"{height}p"
    return None


def _tool_error(exc: MediaToolUnavailableError | MediaToolExecutionError) -> LocalMetadataError:
    if isinstance(exc, MediaToolUnavailableError):
        return LocalMetadataError(
            f"{exc.tool_name}_missing",
            status_code=503,
            reasons=[f"{exc.tool_name} is not installed or not on PATH"],
        )
    return LocalMetadataError(exc.code, reasons=[str(exc)])


def _requested_times(payload: LocalFrameRequest) -> list[float]:
    return [float(value) for value in payload.time_points_seconds if value >= 0]


def _percentage_times(
    percentages: list[float],
    duration_seconds: float,
    *,
    frame_count: int = 9,
) -> list[float]:
    if duration_seconds <= 0:
        return [0.0]
    source_percentages = percentages or _evenly_spaced_percentages(frame_count)
    times: list[float] = []
    for percentage in source_percentages:
        clamped = min(95.0, max(1.0, float(percentage)))
        if duration_seconds <= 0.5:
            times.append(0.0)
        else:
            times.append(max(0.1, min(duration_seconds - 0.25, duration_seconds * clamped / 100)))
    return times or [max(0.0, duration_seconds / 2)]


def _evenly_spaced_percentages(frame_count: int) -> list[float]:
    count = min(36, max(1, int(frame_count)))
    if count == 1:
        return [50.0]
    if count == 9:
        return [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    start = 10.0
    stop = 90.0
    step = (stop - start) / (count - 1)
    return [start + step * index for index in range(count)]


def _fallback_times(frame_count: int) -> list[float]:
    count = min(36, max(1, int(frame_count)))
    return [float(index) for index in range(1, count + 1)]


def _media_item_for_path(path: Path) -> MediaScanItem:
    stat = path.stat()
    return MediaScanItem(
        path=path,
        group_key=path.stem,
        identity=scanner.media_identity(path, stat_result=stat),
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sidecars=[],
    )


def _template_context(record: MetadataRecordData, item: MediaScanItem) -> TemplateContext:
    return TemplateContext(
        number=record.source_id,
        title=record.title,
        original_title=record.original_title,
        studio=record.studio,
        series=record.series,
        release_date=record.release_date,
        actors=[actor.name for actor in record.actors],
        source_filename=item.path.name,
        xchina_id=record.xchina_id,
    )


def _image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            return image.width, image.height
    except OSError:
        return None, None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _clean_text(value)
        if item is None or item in seen:
            continue
        cleaned.append(item)
        seen.add(item)
    return cleaned
