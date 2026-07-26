from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Job,
    MediaItem,
    MediaSidecar,
    OperationPlan as OperationPlanModel,
    SearchCandidate,
    SearchQuery,
)
from backend.app.integrations.xchina import FetchedAsset
from backend.app.schemas.assets import (
    AssetMaterializationPolicy,
    AssetSelection,
    LogicalAsset,
    MissingAsset,
)
from backend.app.schemas.manual import (
    ManualCandidateCard,
    ManualExecutePlanResponse,
    ManualJobRead,
    ManualJobSummary,
    ManualMediaItemRead,
    ManualOrganizeRequest,
    ManualPreviewRequest,
    ManualPreviewResponse,
    ManualScanResponse,
    ManualSearchResponse,
    ManualSelectCandidateResponse,
)
from backend.app.schemas.matching import CandidateMetadata, ExecutionSafety, MatchInput
from backend.app.schemas.media import MediaScanItem, MediaSidecarScanItem
from backend.app.schemas.metadata import MetadataRecordData
from backend.app.schemas.operations import GeneratedArtifact, OperationPlan
from backend.app.schemas.source import SourceSearchResult, SourceVideoDetail
from backend.app.schemas.templates import TemplateContext
from backend.app.services import scanner
from backend.app.services.asset_materializer import AssetAdapter, AssetMaterializer
from backend.app.services.assets import select_assets
from backend.app.services.jobs import ACTIVE_STATES, JobService
from backend.app.services.matching import manual_selection_gate, score_candidate
from backend.app.services.metadata import (
    normalize_source_video,
    persist_metadata_record,
    source_detail_with_search_result_fallbacks,
)
from backend.app.services.nfo import movie_nfo_relative_path, render_movie_nfo
from backend.app.services.operation_executor import (
    OperationExecutionError,
    OperationExecutor,
    OperationJournal,
)
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

logger = logging.getLogger(__name__)


class SearchAdapter(Protocol):
    async def search(self, query: str) -> list[SourceSearchResult]:
        ...

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        ...


class ManualOrganizerError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        reasons: list[str] | None = None,
        rollback: bool = True,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reasons = reasons or [message]
        self.rollback = rollback


class ManualOrganizerService:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        *,
        search_adapter: SearchAdapter | None = None,
        asset_adapter: AssetAdapter | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._search_adapter = search_adapter
        self._asset_adapter = asset_adapter
        self._storage_roots = StorageRootService(settings, session)
        self._jobs = JobService(session)

    def scan(
        self,
        directory: Path,
        *,
        recursive: bool,
        ignore_patterns: list[str],
    ) -> ManualScanResponse:
        logger.info(
            "Manual scan started directory=%s recursive=%s ignore_patterns=%s",
            directory,
            recursive,
            len(ignore_patterns),
        )
        try:
            validation = self._storage_roots.validate_inside_root(directory)
            items = scanner.scan_directory(
                directory,
                recursive=recursive,
                ignore_patterns=tuple(ignore_patterns),
                storage_roots=self._storage_roots,
            )
        except (StorageRootValidationError, ValueError) as exc:
            logger.warning("Manual scan rejected directory=%s error=%s", directory, exc)
            raise ManualOrganizerError(str(exc)) from exc

        jobs: list[ManualJobSummary] = []
        for item in items:
            media = self._persist_media_item(validation.root.id, item, validation.root.path)
            job = self._get_or_create_manual_job(media, item)
            jobs.append(_job_summary(job))
        self._session.flush()
        logger.info(
            "Manual scan completed directory=%s scanned=%s jobs=%s root_id=%s",
            directory,
            len(items),
            len(jobs),
            validation.root.id,
        )
        return ManualScanResponse(scanned_count=len(items), jobs=jobs)

    async def search(
        self,
        *,
        job_id: int | None,
        filename: str | None,
        query: str | None,
        normalized_query: str | None,
    ) -> ManualSearchResponse:
        job = self._job_for_search(job_id, filename=filename, query=query)
        search_text = _normalized_search_text(
            filename=filename,
            query=query,
            normalized_query=normalized_query,
        )
        logger.info(
            "Manual search started job_id=%s query=%r adapter=%s",
            job.id,
            search_text,
            self._search_adapter is not None,
        )
        match_input = MatchInput(search_text=search_text, title=search_text)
        search_row = SearchQuery(
            media_item_id=_first_media_item_id(job),
            query_text=query or filename or search_text,
            normalized_input=match_input.model_dump(mode="json"),
        )
        self._session.add(search_row)
        self._session.flush()

        results: list[SourceSearchResult] = []
        if self._search_adapter is not None:
            try:
                results = await self._search_adapter.search(search_text)
            except Exception as exc:
                logger.warning(
                    "Manual search source unavailable job_id=%s query_id=%s error=%s",
                    job.id,
                    search_row.id,
                    redact_payload(str(exc)),
                )
                payload = _payload(job)
                manual = _manual_payload(payload)
                manual["search_query_id"] = search_row.id
                manual["normalized_query"] = search_text
                manual["candidate_ids"] = []
                manual["search_error"] = "search_source_unavailable"
                job.payload = redact_payload(payload)
                self._session.flush()
                raise ManualOrganizerError(
                    "search_source_unavailable",
                    status_code=503,
                    reasons=["search_source_unavailable"],
                    rollback=False,
                ) from exc
        else:
            logger.warning("Manual search skipped job_id=%s reason=search_adapter_unconfigured", job.id)

        candidates: list[ManualCandidateCard] = []
        for result in results:
            candidate_metadata = _candidate_from_search_result(result)
            score = score_candidate(match_input, candidate_metadata)
            row = SearchCandidate(
                search_query_id=search_row.id,
                source=result.source,
                source_candidate_id=result.source_candidate_id,
                title=result.title,
                source_url=result.url,
                score=score.total,
                candidate_json={
                    "search_result": result.model_dump(mode="json"),
                    "score_breakdown": score.breakdown,
                },
            )
            self._session.add(row)
            self._session.flush()
            candidates.append(_candidate_card(row))

        payload = _payload(job)
        manual = _manual_payload(payload)
        manual["search_query_id"] = search_row.id
        manual["normalized_query"] = search_text
        manual["candidate_ids"] = [candidate.candidate_id for candidate in candidates]
        job.payload = redact_payload(payload)
        self._session.flush()
        top_candidate = candidates[0] if candidates else None
        logger.info(
            "Manual search completed job_id=%s query_id=%s candidates=%s top=%s score=%s",
            job.id,
            search_row.id,
            len(candidates),
            top_candidate.title if top_candidate else None,
            top_candidate.confidence_score if top_candidate else None,
        )
        return ManualSearchResponse(
            job_id=job.id,
            search_query_id=search_row.id,
            query=query or filename or search_text,
            normalized_query=search_text,
            candidates=candidates,
        )

    async def select_candidate(
        self,
        job_id: int,
        *,
        candidate_id: int | None,
        source_url: str | None,
        detail: SourceVideoDetail | None,
        safety: ExecutionSafety,
        strict_assets: bool,
    ) -> ManualSelectCandidateResponse:
        logger.info(
            "Manual candidate selection started job_id=%s candidate_id=%s url_provided=%s strict_assets=%s",
            job_id,
            candidate_id,
            bool(source_url),
            strict_assets,
        )
        job = self._jobs.get_job(job_id)
        row = self._candidate_row(candidate_id, source_url)
        if detail is None:
            if self._search_adapter is None:
                raise ManualOrganizerError("candidate_detail_unavailable")
            detail_url = source_url or (row.source_url if row is not None else None)
            if detail_url is None:
                logger.warning("Manual candidate selection missing detail URL job_id=%s", job_id)
                raise ManualOrganizerError("candidate_detail_url_required")
            detail = await self._search_adapter.fetch_video_detail(detail_url)

        detail = source_detail_with_search_result_fallbacks(
            detail,
            _search_result_from_candidate(row),
        )
        record = normalize_source_video(detail)
        selection = select_assets(record)
        effective_safety = _manual_safety(job, safety, selection, strict_assets)
        candidate_metadata = _candidate_from_detail(
            detail,
            strict_assets=strict_assets,
            selection=selection,
        )
        decision = manual_selection_gate(candidate_metadata, effective_safety)
        card = _candidate_card(row) if row is not None else _candidate_card_from_detail(detail)
        if decision.action != "manual_approved":
            logger.warning(
                "Manual candidate selection requires review job_id=%s candidate_id=%s reasons=%s",
                job.id,
                card.candidate_id,
                decision.reasons,
            )
            self._record_job_payload(
                job,
                {
                    "selection_refused": True,
                    "selection_refusal_reasons": decision.reasons,
                    "selected_candidate_id": card.candidate_id,
                    "selected_source_url": detail.source_url,
                    "selected_detail": detail.model_dump(mode="json"),
                    "metadata": record.model_dump(mode="json"),
                },
            )
            if job.state == "searching":
                self._jobs.transition_job(
                    job.id,
                    "review_required",
                    payload={"candidate_id": card.candidate_id, "reasons": decision.reasons},
                )
            self._session.flush()
            return ManualSelectCandidateResponse(
                job_id=job.id,
                accepted=False,
                reasons=decision.reasons,
                selected_candidate=card,
                metadata=record.model_dump(mode="json"),
            )

        metadata_row = persist_metadata_record(
            self._session,
            record,
            media_item_id=_first_media_item_id(job),
        )
        self._record_job_payload(
            job,
            {
                "selected_candidate_id": card.candidate_id,
                "selected_source_url": detail.source_url,
                "selected_detail": detail.model_dump(mode="json"),
                "metadata_record_id": metadata_row.id,
                "metadata": record.model_dump(mode="json"),
            },
        )
        if job.state in {"review_required", "searching"}:
            self._jobs.transition_job(
                job.id,
                "matched",
                payload={"candidate_id": card.candidate_id},
            )
        self._session.flush()
        logger.info(
            "Manual candidate selection accepted job_id=%s candidate_id=%s metadata_id=%s title=%s",
            job.id,
            card.candidate_id,
            metadata_row.id,
            record.title,
        )
        return ManualSelectCandidateResponse(
            job_id=job.id,
            accepted=True,
            selected_candidate=card,
            metadata_record_id=metadata_row.id,
            metadata=record.model_dump(mode="json"),
        )

    async def preview(
        self,
        job_id: int,
        payload: ManualPreviewRequest,
    ) -> ManualPreviewResponse:
        logger.info(
            "Manual preview started job_id=%s destination=%s mode=%s asset_policy=%s snapshot=%s",
            job_id,
            payload.destination_root,
            payload.mode,
            payload.asset_policy,
            payload.include_source_snapshot,
        )
        job = self._jobs.get_job(job_id)
        record = _selected_metadata(job)
        media_items = _media_items_from_payload(job)
        if not media_items:
            raise ManualOrganizerError("media_required_for_preview")
        try:
            self._storage_roots.validate_inside_root(payload.destination_root)
        except StorageRootValidationError as exc:
            logger.warning(
                "Manual preview rejected job_id=%s destination=%s error=%s",
                job_id,
                payload.destination_root,
                exc,
            )
            raise ManualOrganizerError(str(exc)) from exc

        materialized = await self._materialize_assets(
            record,
            destination_root=payload.destination_root,
            strict=payload.asset_policy == "strict",
            include_source_snapshot=payload.include_source_snapshot,
        )
        if materialized.failed:
            logger.warning(
                "Manual preview asset materialization failed job_id=%s missing_required=%s",
                job.id,
                len([item for item in materialized.missing if item.required]),
            )
            raise ManualOrganizerError(
                "strict_asset_materialization_failed",
                reasons=[item.reason for item in materialized.missing if item.required],
            )

        template = preview_template(
            folder_templates=payload.folder_templates,
            filename_template=payload.filename_template,
            context=_template_context(record, media_items[0]),
        )
        generated: list[GeneratedArtifact] = []
        if template.filename:
            generated = [
                GeneratedArtifact(
                    relative_path=movie_nfo_relative_path(template.filename),
                    artifact_type="nfo",
                    content_text=render_movie_nfo(record).decode("utf-8"),
                    allow_replace_existing=True,
                )
            ]
        try:
            plan = OrganizerPlanService(self._session, self._storage_roots).create_plan(
                mode=payload.mode,
                media_items=media_items,
                destination_root=payload.destination_root,
                template_preview=template,
                materialized_assets=materialized,
                generated_artifacts=generated,
                job_id=job.id,
            )
        except OperationPlanConflictError as exc:
            logger.warning(
                "Manual preview blocked by conflicts job_id=%s conflicts=%s",
                job.id,
                len(exc.conflicts),
            )
            raise ManualOrganizerError(
                "destination_collision",
                status_code=409,
                reasons=[conflict.reason for conflict in exc.conflicts],
            ) from exc
        except OperationPlanSafetyError as exc:
            raise ManualOrganizerError(str(exc)) from exc

        row = self._plan_row(plan.plan_id)
        row.status = "approved"
        self._record_job_payload(job, {"plan_id": plan.plan_id, "previewed_plan": plan.snapshot_json()})
        self._advance_preview_job(job)
        self._session.flush()
        logger.info(
            "Manual preview completed job_id=%s plan_id=%s steps=%s assets=%s missing=%s",
            job.id,
            plan.plan_id,
            len(plan.steps),
            len(materialized.assets),
            len(materialized.missing),
        )
        return ManualPreviewResponse(
            job_id=job.id,
            plan_id=plan.plan_id,
            metadata=record.model_dump(mode="json"),
            materialized_assets=[
                asset.model_dump(mode="json") for asset in materialized.assets
            ],
            missing_assets=[item.model_dump(mode="json") for item in materialized.missing],
            plan=plan.snapshot_json(),
        )

    async def organize(
        self,
        job_id: int,
        payload: ManualOrganizeRequest,
    ) -> ManualExecutePlanResponse:
        safe_payload = payload.model_copy(
            update={"mode": _organization_mode_or_copy(payload.mode)}
        )
        plan_preview = await self.preview(job_id, safe_payload)
        return self.execute_plan(
            plan_preview.plan_id,
            approved=True,
            plan_version=int(plan_preview.plan.get("version", 1)),
        )

    def execute_plan(
        self,
        plan_id: str,
        *,
        approved: bool,
        plan_version: int,
    ) -> ManualExecutePlanResponse:
        logger.info(
            "Manual execute requested plan_id=%s approved=%s version=%s",
            plan_id,
            approved,
            plan_version,
        )
        if not approved:
            logger.warning("Manual execute rejected plan_id=%s reason=approval_required", plan_id)
            raise ManualOrganizerError("plan_approval_required")
        row = self._plan_row(plan_id)
        if int(row.version) != plan_version:
            raise ManualOrganizerError("plan_version_mismatch")
        if row.status not in {"approved", "planned"}:
            raise ManualOrganizerError(f"plan_not_executable:{row.status}")
        plan = OperationPlan.model_validate(row.plan_json).model_copy(
            update={"database_id": row.id}
        )
        job = self._session.get(Job, row.job_id) if row.job_id is not None else None
        if job is not None and job.state == "ready":
            self._jobs.transition_job(job.id, "executing", payload={"plan_id": plan_id})
        try:
            OperationExecutor(
                self._storage_roots,
                journal=OperationJournal(self._session),
            ).execute(plan)
        except OperationExecutionError as exc:
            row.status = "failed"
            logger.error(
                "Manual execute failed plan_id=%s job_id=%s error_code=%s",
                plan_id,
                row.job_id,
                exc.error_code,
            )
            if job is not None and "failed" in _valid_next_states(job.state):
                self._jobs.transition_job(
                    job.id,
                    "failed",
                    payload={"plan_id": plan_id, "error_code": exc.error_code},
                )
            self._session.flush()
            raise ManualOrganizerError(exc.error_code, status_code=409) from exc
        row.status = "completed"
        if job is not None and job.state == "executing":
            self._jobs.transition_job(job.id, "completed", payload={"plan_id": plan_id})
        self._session.flush()
        logger.info("Manual execute completed plan_id=%s job_id=%s", plan_id, row.job_id)
        return ManualExecutePlanResponse(
            plan_id=plan_id,
            job_id=row.job_id,
            state=row.status,
        )

    def get_job(self, job_id: int) -> ManualJobRead:
        job = self._jobs.get_job(job_id)
        payload = redact_payload(_payload(job))
        candidate_ids = _manual_payload(payload).get("candidate_ids") or []
        candidates = [
            _candidate_card(row)
            for row in self._session.scalars(
                select(SearchCandidate)
                .where(SearchCandidate.id.in_(candidate_ids))
                .order_by(SearchCandidate.id)
            )
        ] if candidate_ids else []
        manual = _manual_payload(payload)
        return ManualJobRead(
            job_id=job.id,
            state=job.state,
            payload=payload,
            candidates=candidates,
            selected_metadata=manual.get("metadata"),
            plan_id=manual.get("plan_id"),
        )

    def _persist_media_item(
        self,
        storage_root_id: int,
        item: MediaScanItem,
        storage_root_path: str,
    ) -> MediaItem:
        media = self._session.scalar(
            select(MediaItem).where(
                or_(MediaItem.identity == item.identity, MediaItem.path == str(item.path))
            )
        )
        relative_path = str(Path(item.path).relative_to(Path(storage_root_path)))
        if media is None:
            media = MediaItem(
                storage_root_id=storage_root_id,
                path=str(item.path),
                relative_path=relative_path,
                filename=Path(item.path).name,
                group_key=item.group_key,
                multipart_index=item.multipart_index,
                identity=item.identity,
                size_bytes=item.size_bytes,
                mtime_ns=item.mtime_ns,
            )
            self._session.add(media)
            self._session.flush()
        else:
            media.path = str(item.path)
            media.relative_path = relative_path
            media.filename = Path(item.path).name
            media.group_key = item.group_key
            media.multipart_index = item.multipart_index
            media.size_bytes = item.size_bytes
            media.mtime_ns = item.mtime_ns
        for sidecar in item.sidecars:
            existing = self._session.scalar(
                select(MediaSidecar).where(
                    MediaSidecar.media_item_id == media.id,
                    MediaSidecar.path == str(sidecar.path),
                )
            )
            if existing is None:
                self._session.add(
                    MediaSidecar(
                        media_item_id=media.id,
                        path=str(sidecar.path),
                        kind=sidecar.kind,
                        extension=Path(sidecar.path).suffix.lower(),
                    )
                )
        self._session.flush()
        return media

    def _get_or_create_manual_job(self, media: MediaItem, item: MediaScanItem) -> Job:
        existing = self._session.scalar(
            select(Job).where(
                Job.manual.is_(True),
                Job.media_identity == media.identity,
                Job.state.in_(ACTIVE_STATES),
            )
        )
        if existing is not None:
            return existing
        return self._jobs.create_job(
            media_identity=media.identity,
            manual=True,
            state="review_required",
            payload={
                "manual": {
                    "media_item_ids": [media.id],
                    "media_items": [_media_item_payload(item)],
                }
            },
        )

    def _job_for_search(
        self,
        job_id: int | None,
        *,
        filename: str | None,
        query: str | None,
    ) -> Job:
        if job_id is not None:
            return self._jobs.get_job(job_id)
        identity_material = filename or query or "manual-query"
        identity = "manual-query:" + hashlib.sha256(
            identity_material.encode("utf-8")
        ).hexdigest()
        existing = self._session.scalar(
            select(Job).where(
                Job.manual.is_(True),
                Job.media_identity == identity,
                Job.state.in_(ACTIVE_STATES),
            )
        )
        if existing is not None:
            return existing
        return self._jobs.create_job(
            media_identity=identity,
            manual=True,
            state="review_required",
            payload={"manual": {"filename": filename, "query": query}},
        )

    def _candidate_row(
        self,
        candidate_id: int | None,
        source_url: str | None,
    ) -> SearchCandidate | None:
        if candidate_id is not None:
            row = self._session.get(SearchCandidate, candidate_id)
            if row is None:
                raise ManualOrganizerError("candidate_not_found", status_code=404)
            return row
        if source_url is None:
            return None
        return self._session.scalar(
            select(SearchCandidate).where(SearchCandidate.source_url == source_url)
        )

    def _materialize_assets(
        self,
        record: MetadataRecordData,
        *,
        destination_root: Path,
        strict: bool,
        include_source_snapshot: bool,
    ):
        selection = select_assets(
            record,
            include_source_snapshot=include_source_snapshot,
        )
        if self._asset_adapter is None:
            selection = _inline_only_selection(selection)
        materializer = AssetMaterializer(
            self._asset_adapter or _InlineOnlyAssetAdapter(),
            destination_root / ".xona-cache",
            session=self._session,
        )
        return materializer.materialize(
            selection,
            AssetMaterializationPolicy(strict=strict),
        )

    def _plan_row(self, plan_id: str) -> OperationPlanModel:
        row = self._session.scalar(
            select(OperationPlanModel).where(OperationPlanModel.plan_id == plan_id)
        )
        if row is None:
            raise ManualOrganizerError("plan_not_found", status_code=404)
        return row

    def _record_job_payload(self, job: Job, values: dict[str, Any]) -> None:
        payload = _payload(job)
        manual = _manual_payload(payload)
        manual.update(redact_payload(values))
        job.payload = redact_payload(payload)

    def _advance_preview_job(self, job: Job) -> None:
        transitions = [
            ("matched", "scraping"),
            ("scraping", "materializing_assets"),
            ("materializing_assets", "planning"),
            ("planning", "ready"),
        ]
        for from_state, to_state in transitions:
            if job.state == from_state:
                self._jobs.transition_job(job.id, to_state)


class _InlineOnlyAssetAdapter:
    async def fetch_asset(
        self,
        url: str,
        *,
        referer_url: str | None = None,
    ) -> FetchedAsset:
        raise RuntimeError(f"remote_asset_disabled:{redact_payload(url)}")


def _inline_only_selection(selection: AssetSelection) -> AssetSelection:
    assets: list[LogicalAsset] = []
    missing = list(selection.missing_required)
    for asset in selection.assets:
        if asset.inline_bytes is not None:
            assets.append(asset)
        elif asset.required:
            missing.append(
                MissingAsset(
                    kind=asset.kind,
                    relative_path=asset.relative_path,
                    required=True,
                    reason="asset_adapter_unconfigured",
                )
            )
    return AssetSelection(assets=assets, missing_required=missing)


def _media_item_payload(item: MediaScanItem) -> dict[str, Any]:
    return {
        **item.model_dump(mode="json"),
        "sidecars": [sidecar.model_dump(mode="json") for sidecar in item.sidecars],
    }


def _job_summary(job: Job) -> ManualJobSummary:
    return ManualJobSummary(
        job_id=job.id,
        state=job.state,
        media_identity=job.media_identity,
        media_items=[
            ManualMediaItemRead.model_validate(item)
            for item in _manual_payload(_payload(job)).get("media_items", [])
        ],
    )


def _payload(job: Job) -> dict[str, Any]:
    payload = deepcopy(dict(job.payload or {}))
    manual = payload.get("manual")
    if not isinstance(manual, dict):
        payload["manual"] = {}
    return payload


def _manual_payload(payload: dict[str, Any]) -> dict[str, Any]:
    manual = payload.setdefault("manual", {})
    if not isinstance(manual, dict):
        payload["manual"] = {}
        return payload["manual"]
    return manual


def _normalized_search_text(
    *,
    filename: str | None,
    query: str | None,
    normalized_query: str | None,
) -> str:
    source = normalized_query or query or filename
    if not source:
        raise ManualOrganizerError("search_query_required")
    if source == filename:
        source = Path(source).stem
    normalized = " ".join(str(source).replace("_", " ").replace(".", " ").split())
    if not normalized:
        raise ManualOrganizerError("search_query_required")
    return normalized


def _candidate_from_search_result(result: SourceSearchResult) -> CandidateMetadata:
    return CandidateMetadata(
        source_id=result.source_candidate_id,
        title=result.title,
        identifiers=[result.source_candidate_id],
        actors=[actor.name for actor in result.actors],
        studio=result.studio,
        series=result.series,
        release_date=result.release_date,
        complete=True,
        asset_ready=bool(result.thumbnail_url),
        unique_detail=True,
    )


def _candidate_from_detail(
    detail: SourceVideoDetail,
    *,
    strict_assets: bool,
    selection: AssetSelection,
) -> CandidateMetadata:
    return CandidateMetadata(
        source_id=detail.source_id,
        title=detail.title,
        identifiers=[detail.source_id],
        actors=[actor.name for actor in detail.actors],
        studio=detail.studio,
        series=detail.series,
        release_date=detail.release_date,
        complete=detail.is_complete,
        asset_ready=(not strict_assets) or not selection.missing_required,
        unique_detail=True,
    )


def _candidate_card(row: SearchCandidate) -> ManualCandidateCard:
    payload = row.candidate_json or {}
    result = payload.get("search_result") if isinstance(payload, dict) else {}
    result = result if isinstance(result, dict) else {}
    breakdown = payload.get("score_breakdown") if isinstance(payload, dict) else {}
    actors = result.get("actors") or []
    return ManualCandidateCard(
        candidate_id=row.id,
        source=row.source,
        source_candidate_id=row.source_candidate_id,
        title=row.title,
        image_url=result.get("thumbnail_url"),
        actors=[
            str(actor.get("name"))
            for actor in actors
            if isinstance(actor, dict) and actor.get("name")
        ],
        studio=result.get("studio"),
        series=result.get("series"),
        release_date=result.get("release_date"),
        url=row.source_url,
        confidence_score=int(row.score or 0),
        score_breakdown={
            str(key): int(value)
            for key, value in (breakdown or {}).items()
            if isinstance(value, int)
        },
    )


def _search_result_from_candidate(row: SearchCandidate | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = row.candidate_json or {}
    result = payload.get("search_result") if isinstance(payload, dict) else None
    return result if isinstance(result, dict) else None


def _candidate_card_from_detail(detail: SourceVideoDetail) -> ManualCandidateCard:
    return ManualCandidateCard(
        candidate_id=0,
        source=detail.source,
        source_candidate_id=detail.source_id,
        title=detail.title,
        image_url=(detail.poster.url if detail.poster is not None else None),
        actors=[actor.name for actor in detail.actors],
        studio=detail.studio,
        series=detail.series,
        release_date=detail.release_date,
        url=detail.source_url,
        confidence_score=0,
    )


def _first_media_item_id(job: Job) -> int | None:
    ids = _manual_payload(_payload(job)).get("media_item_ids") or []
    if not ids:
        return None
    return int(ids[0])


def _manual_safety(
    job: Job,
    safety: ExecutionSafety,
    selection: AssetSelection,
    strict_assets: bool,
) -> ExecutionSafety:
    media_items = _media_items_from_payload(job)
    unresolved = safety.unresolved_multipart or (
        len(media_items) == 1 and media_items[0].multipart_index is not None
    )
    return safety.model_copy(
        update={
            "unresolved_multipart": unresolved,
            "strict_assets_missing": safety.strict_assets_missing
            or (strict_assets and bool(selection.missing_required)),
        }
    )


def _selected_metadata(job: Job) -> MetadataRecordData:
    metadata = _manual_payload(_payload(job)).get("metadata")
    if not isinstance(metadata, dict):
        raise ManualOrganizerError("selected_metadata_required")
    return MetadataRecordData.model_validate(metadata)


def _selected_detail(job: Job) -> SourceVideoDetail:
    detail = _manual_payload(_payload(job)).get("selected_detail")
    if not isinstance(detail, dict):
        raise ManualOrganizerError("selected_detail_required")
    return SourceVideoDetail.model_validate(detail)


def _media_items_from_payload(job: Job) -> list[MediaScanItem]:
    items = _manual_payload(_payload(job)).get("media_items") or []
    result: list[MediaScanItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sidecars = [
            MediaSidecarScanItem.model_validate(sidecar)
            for sidecar in item.get("sidecars", [])
            if isinstance(sidecar, dict)
        ]
        material = dict(item)
        material["sidecars"] = sidecars
        result.append(MediaScanItem.model_validate(material))
    return result


def _template_context(record: MetadataRecordData, item: MediaScanItem) -> TemplateContext:
    return TemplateContext(
        number=record.xchina_id,
        title=record.title,
        original_title=record.original_title,
        studio=record.studio,
        series=record.series,
        release_date=record.release_date,
        actors=[actor.name for actor in record.actors],
        source_filename=Path(item.path).name,
        xchina_id=record.xchina_id,
    )


def _valid_next_states(state: str) -> set[str]:
    from backend.app.services.jobs import VALID_TRANSITIONS

    return VALID_TRANSITIONS[state]


def _organization_mode_or_copy(value: str) -> str:
    return "copy" if value == "preview" else value
