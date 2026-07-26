from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.integrations.flaresolverr import FlareSolverrClient
from backend.app.integrations.xchina import XChinaAdapter
from backend.app.integrations.xchina_config import xchina_base_url, xchina_max_search_pages
from backend.app.db.models import (
    Job,
    MediaItem,
    OperationPlan as OperationPlanModel,
    SearchCandidate,
    SearchQuery,
    WatchRule,
)
from backend.app.integrations.emby import EmbyPathMapper
from backend.app.schemas.assets import AssetMaterializationPolicy, MaterializedAsset
from backend.app.schemas.matching import CandidateMetadata, ExecutionSafety, MatchInput
from backend.app.schemas.media import MediaScanItem, MediaSidecarScanItem
from backend.app.schemas.metadata import MetadataRecordData
from backend.app.schemas.operations import GeneratedArtifact, OperationPlan, OrganizationMode
from backend.app.schemas.source import SourceSearchResult, SourceVideoDetail
from backend.app.schemas.templates import TemplateContext
from backend.app.services.asset_materializer import AssetAdapter, AssetMaterializer
from backend.app.services.assets import select_assets
from backend.app.services.jobs import JobService
from backend.app.services.matching import can_auto_execute, score_candidate
from backend.app.services.metadata import (
    normalize_source_video,
    persist_metadata_record,
    source_detail_with_search_result_fallbacks,
)
from backend.app.services.nfo import movie_nfo_relative_path, render_movie_nfo
from backend.app.services.normalization import normalize_filename_for_search
from backend.app.services.operation_executor import OperationExecutor, OperationJournal
from backend.app.services.organizer_plans import OrganizerPlanService
from backend.app.services.settings_store import SettingsStore
from backend.app.services.storage_roots import StorageRootService
from backend.app.services.templates import preview_template

logger = logging.getLogger(__name__)


DEFAULT_TRANSITIONS = {
    "discovered": "waiting_stable",
    "waiting_stable": "searching",
    "matched": "scraping",
    "scraping": "materializing_assets",
    "materializing_assets": "planning",
    "planning": "ready",
    "ready": "executing",
    "executing": "notifying_emby",
    "notifying_emby": "completed",
}

JobHandler = Callable[[Job], str | None]


class SearchAdapter(Protocol):
    async def search(self, query: str) -> list[SourceSearchResult]: ...

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail: ...


class EmbyNotifyClient(Protocol):
    async def scan_library(self) -> None: ...

    async def find_item_by_path(self, emby_path: str) -> dict[str, Any] | None: ...

    async def refresh_item(self, item_id: str) -> None: ...


class Worker:
    def __init__(
        self,
        sessionmaker: sessionmaker[Session],
        *,
        settings: Settings | None = None,
        search_adapter: SearchAdapter | None = None,
        asset_adapter: AssetAdapter | None = None,
        emby_client: EmbyNotifyClient | None = None,
        worker_id: str | None = None,
        handlers: dict[str, JobHandler] | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._search_adapter = search_adapter
        self._asset_adapter = asset_adapter
        self._emby_client = emby_client
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex}"
        self._handlers = handlers or {}
        self._poll_interval_seconds = poll_interval_seconds
        self._stop = asyncio.Event()
        self._auto_flaresolverr_client: FlareSolverrClient | None = None
        self._auto_flaresolverr_client_key: tuple[str, str] | None = None

    async def run_once(self) -> bool:
        with self._sessionmaker() as session:
            service = JobService(session)
            job = service.lease_next(worker_id=self._worker_id)
            if job is None:
                session.commit()
                return False
            if job.state == "cancelled":
                logger.info("Worker skipped cancelled job job_id=%s", job.id)
                service.release_lease(job)
                session.commit()
                return False
            try:
                logger.info(
                    "Worker processing job_id=%s state=%s manual=%s",
                    job.id,
                    job.state,
                    job.manual,
                )
                target_state = await self._target_state(session, job)
                if target_state is None:
                    logger.info(
                        "Worker released job without state change job_id=%s state=%s",
                        job.id,
                        job.state,
                    )
                    service.release_lease(job)
                else:
                    logger.info(
                        "Worker job step completed job_id=%s %s->%s",
                        job.id,
                        job.state,
                        target_state,
                    )
                    service.transition_job(job.id, target_state)
                    service.release_lease(job)
                session.commit()
                return True
            except Exception as exc:
                logger.exception(
                    "Worker job step failed job_id=%s state=%s error=%s",
                    job.id,
                    job.state,
                    exc.__class__.__name__,
                )
                if job.state == "notifying_emby":
                    service.transition_job(
                        job.id,
                        "local_complete_emby_failed",
                        payload={
                            "error_code": exc.__class__.__name__,
                            "local_operations_complete": True,
                        },
                    )
                    service.release_lease(job)
                else:
                    service.schedule_retry(
                        job,
                        error_code=exc.__class__.__name__,
                    )
                session.commit()
                return True

    async def run_forever(self) -> None:
        logger.info(
            "Worker loop started worker_id=%s poll_interval=%s",
            self._worker_id,
            self._poll_interval_seconds,
        )
        while not self._stop.is_set():
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self._poll_interval_seconds)
        logger.info("Worker loop stopped worker_id=%s", self._worker_id)

    def stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        client = self._auto_flaresolverr_client
        self._auto_flaresolverr_client = None
        self._auto_flaresolverr_client_key = None
        if client is not None:
            await client.close()

    @asynccontextmanager
    async def _auto_adapters(
        self,
        session: Session,
    ) -> AsyncIterator[tuple[SearchAdapter | None, AssetAdapter | None]]:
        search_adapter = self._search_adapter
        asset_adapter = self._asset_adapter
        if search_adapter is None or asset_adapter is None:
            settings = self._require_settings()
            store_settings = SettingsStore(session).xchina_settings()
            endpoint = settings.flaresolverr_url or store_settings.get("flaresolverr_url")
            if endpoint:
                flaresolverr = await self._shared_auto_flaresolverr_client(
                    str(endpoint),
                    settings.proxy_url or store_settings.get("proxy_url"),
                )
                adapter = XChinaAdapter(
                    flaresolverr,
                    session,
                    base_url=xchina_base_url(store_settings),
                    max_search_pages=xchina_max_search_pages(store_settings),
                )
                if search_adapter is None:
                    search_adapter = adapter
                if asset_adapter is None:
                    asset_adapter = adapter
        yield search_adapter, asset_adapter

    async def _shared_auto_flaresolverr_client(
        self,
        endpoint: str,
        proxy_url: object | None,
    ) -> FlareSolverrClient:
        key = (endpoint, str(proxy_url or ""))
        if self._auto_flaresolverr_client is None or self._auto_flaresolverr_client_key != key:
            await self.close()
            self._auto_flaresolverr_client = FlareSolverrClient(
                endpoint,
                proxy_url=str(proxy_url) if proxy_url else None,
            )
            self._auto_flaresolverr_client_key = key
        return self._auto_flaresolverr_client

    async def _target_state(self, session: Session, job: Job) -> str | None:
        handler = self._handlers.get(job.state)
        if handler is not None:
            result = handler(job)
            if asyncio.iscoroutine(result):
                return await result
            return result
        if self._settings is not None and not job.manual:
            return await self._auto_target_state(session, job)
        return DEFAULT_TRANSITIONS.get(job.state)

    async def _auto_target_state(self, session: Session, job: Job) -> str | None:
        self._require_settings()
        if job.state == "discovered":
            return "waiting_stable"
        if job.state == "waiting_stable":
            return "searching"
        if job.state == "searching":
            return await self._search_gate_and_materialize(session, job)
        if job.state == "matched":
            return "scraping"
        if job.state == "scraping":
            return "materializing_assets"
        if job.state == "materializing_assets":
            return "planning"
        if job.state == "planning":
            self._create_operation_plan(session, job)
            return "ready"
        if job.state == "ready":
            return "executing"
        if job.state == "executing":
            self._execute_operation_plan(session, job)
            return "notifying_emby" if _emby_enabled(session, job) else "completed"
        if job.state == "notifying_emby":
            await self._notify_emby(session, job)
            return "completed"
        return DEFAULT_TRANSITIONS.get(job.state)

    async def _search_gate_and_materialize(
        self,
        session: Session,
        job: Job,
    ) -> str:
        settings = self._require_settings()
        rule = _rule_for_job(session, job)
        payload = _payload(job)
        media_path = Path(str(payload.get("last_seen_path") or ""))
        logger.info(
            "Auto search started job_id=%s rule_id=%s path=%s threshold=%s",
            job.id,
            rule.rule_id,
            media_path,
            rule.confidence_threshold,
        )
        media_item = _persist_media_item(
            session,
            settings,
            media_path,
            media_identity=job.media_identity,
        )
        media_scan_item = _media_scan_item(media_path, media_identity=job.media_identity)
        match_input, query = _match_input(media_path)
        auto_payload = _auto_payload(payload)
        auto_payload.update(
            {
                "media_item_ids": [media_item.id],
                "media_items": [_media_item_payload(media_scan_item)],
                "normalized_query": query,
            }
        )

        async with self._auto_adapters(session) as (search_adapter, asset_adapter):
            if search_adapter is None:
                auto_payload["gate_reasons"] = ["search_adapter_unconfigured"]
                job.payload = redact_payload(payload)
                logger.warning(
                    "Auto search blocked job_id=%s reason=search_adapter_unconfigured", job.id
                )
                return "review_required"

            search_row = SearchQuery(
                media_item_id=media_item.id,
                query_text=query,
                normalized_input=match_input.model_dump(mode="json"),
            )
            session.add(search_row)
            session.flush()

            try:
                results = await search_adapter.search(query)
            except Exception as exc:
                auto_payload["gate_reasons"] = ["search_source_unavailable"]
                auto_payload["search_query_id"] = search_row.id
                auto_payload["candidate_ids"] = []
                auto_payload["search_error"] = "search_source_unavailable"
                job.payload = redact_payload(payload)
                logger.warning(
                    "Auto search source unavailable job_id=%s query=%r error=%s",
                    job.id,
                    query,
                    redact_payload(str(exc)),
                )
                return "review_required"
            logger.info(
                "Auto search results job_id=%s query=%r candidates=%s", job.id, query, len(results)
            )
            candidates: list[CandidateMetadata] = []
            rows_by_source_id: dict[str, SearchCandidate] = {}
            for result in results:
                candidate = _candidate_from_search_result(result)
                score = score_candidate(match_input, candidate)
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
                session.add(row)
                session.flush()
                candidates.append(candidate)
                rows_by_source_id[result.source_candidate_id] = row

            ranked_scores = sorted(
                (score_candidate(match_input, candidate) for candidate in candidates),
                key=lambda score: (score.total, score.candidate.source_id),
                reverse=True,
            )
            lead = (
                ranked_scores[0].total - ranked_scores[1].total if len(ranked_scores) > 1 else None
            )
            decision = can_auto_execute(
                match_input,
                candidates,
                ExecutionSafety(),
                auto_threshold=rule.confidence_threshold,
                required_lead=10,
            )
            auto_payload.update(_decision_payload(decision, lead=lead))
            auto_payload["search_query_id"] = search_row.id
            auto_payload["candidate_ids"] = [row.id for row in rows_by_source_id.values()]
            if decision.action != "auto_approved" or decision.selected is None:
                job.payload = redact_payload(payload)
                logger.info(
                    "Auto gate requires review job_id=%s action=%s reasons=%s lead=%s",
                    job.id,
                    decision.action,
                    decision.reasons,
                    lead,
                )
                return "review_required"

            selected_row = rows_by_source_id.get(decision.selected.source_id)
            if selected_row is None:
                auto_payload["gate_reasons"] = ["selected_candidate_missing"]
                job.payload = redact_payload(payload)
                logger.warning("Auto gate selected candidate missing job_id=%s", job.id)
                return "review_required"

            logger.info(
                "Auto detail fetch started job_id=%s candidate_id=%s",
                job.id,
                selected_row.id,
            )
            detail = await search_adapter.fetch_video_detail(selected_row.source_url)
            detail = source_detail_with_search_result_fallbacks(
                detail,
                _search_result_from_candidate(selected_row),
            )
            record = normalize_source_video(detail)
            selection = select_assets(
                record,
                include_source_snapshot=_include_source_snapshot(session, rule),
            )
            strict_assets_missing = rule.asset_policy == "strict" and bool(
                selection.missing_required
            )
            detail_candidate = _candidate_from_detail(
                detail,
                strict_assets=rule.asset_policy == "strict",
                strict_assets_missing=strict_assets_missing,
            )
            detail_decision = can_auto_execute(
                match_input,
                [detail_candidate],
                ExecutionSafety(strict_assets_missing=strict_assets_missing),
                auto_threshold=rule.confidence_threshold,
                required_lead=10,
            )
            if detail_decision.action != "auto_approved":
                auto_payload.update(_decision_payload(detail_decision, lead=lead))
                job.payload = redact_payload(payload)
                logger.info(
                    "Auto detail gate requires review job_id=%s action=%s reasons=%s",
                    job.id,
                    detail_decision.action,
                    detail_decision.reasons,
                )
                return "review_required"
            if asset_adapter is None:
                auto_payload["gate_reasons"] = ["asset_adapter_unconfigured"]
                job.payload = redact_payload(payload)
                logger.warning(
                    "Auto asset materialization blocked job_id=%s reason=asset_adapter_unconfigured",
                    job.id,
                )
                return "review_required"

            logger.info(
                "Auto asset materialization started job_id=%s strict=%s",
                job.id,
                rule.asset_policy == "strict",
            )
            materialized = await AssetMaterializer(
                asset_adapter,
                Path(rule.destination_directory) / ".xona-cache",
                session=session,
            ).materialize(
                selection,
                AssetMaterializationPolicy(strict=rule.asset_policy == "strict"),
            )
            if materialized.failed:
                auto_payload["gate_reasons"] = [
                    item.reason for item in materialized.missing if item.required
                ] or ["asset_materialization_failed"]
                auto_payload["missing_assets"] = [
                    item.model_dump(mode="json") for item in materialized.missing
                ]
                job.payload = redact_payload(payload)
                logger.warning(
                    "Auto asset materialization failed job_id=%s missing_required=%s",
                    job.id,
                    len([item for item in materialized.missing if item.required]),
                )
                return "review_required"

            metadata_row = persist_metadata_record(
                session,
                record,
                media_item_id=media_item.id,
            )
            auto_payload.update(
                {
                    "gate_reasons": [],
                    "selected_candidate_id": selected_row.id,
                    "selected_source_url": detail.source_url,
                    "selected_detail": detail.model_dump(mode="json"),
                    "metadata_record_id": metadata_row.id,
                    "metadata": record.model_dump(mode="json"),
                    "materialized_assets": [
                        asset.model_dump(mode="json") for asset in materialized.assets
                    ],
                    "missing_assets": [
                        item.model_dump(mode="json") for item in materialized.missing
                    ],
                }
            )
            job.payload = redact_payload(payload)
            logger.info(
                "Auto match accepted job_id=%s candidate_id=%s metadata_id=%s assets=%s",
                job.id,
                selected_row.id,
                metadata_row.id,
                len(materialized.assets),
            )
        return "matched"

    def _create_operation_plan(self, session: Session, job: Job) -> None:
        settings = self._require_settings()
        rule = _rule_for_job(session, job)
        payload = _payload(job)
        auto = _auto_payload(payload)
        record = MetadataRecordData.model_validate(auto["metadata"])
        media_items = [_media_scan_item_from_payload(item) for item in auto["media_items"]]
        materialized = [
            MaterializedAsset.model_validate(asset)
            for asset in auto.get("materialized_assets", [])
            if isinstance(asset, dict)
        ]
        template = preview_template(
            folder_templates=list(rule.folder_templates),
            filename_template=rule.filename_template,
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
        plan = OrganizerPlanService(
            session,
            StorageRootService(settings, session),
        ).create_plan(
            mode=_organization_mode(rule.organization_mode),
            media_items=media_items,
            destination_root=Path(rule.destination_directory),
            template_preview=template,
            materialized_assets=materialized,
            generated_artifacts=generated,
            job_id=job.id,
        )
        auto["plan_id"] = plan.plan_id
        auto["previewed_plan"] = plan.snapshot_json()
        job.payload = redact_payload(payload)
        logger.info(
            "Auto plan created job_id=%s plan_id=%s steps=%s", job.id, plan.plan_id, len(plan.steps)
        )

    def _execute_operation_plan(self, session: Session, job: Job) -> None:
        settings = self._require_settings()
        payload = _payload(job)
        auto = _auto_payload(payload)
        plan_id = str(auto.get("plan_id") or "")
        row = None
        if plan_id:
            row = session.scalar(
                select(OperationPlanModel).where(OperationPlanModel.plan_id == plan_id)
            )
        if row is None:
            row = session.scalar(
                select(OperationPlanModel)
                .where(OperationPlanModel.job_id == job.id)
                .order_by(OperationPlanModel.created_at.desc(), OperationPlanModel.id.desc())
                .limit(1)
            )
        if row is None:
            raise RuntimeError("operation_plan_missing")
        plan = OperationPlan.model_validate(row.plan_json).model_copy(
            update={"database_id": row.id}
        )
        OperationExecutor(
            StorageRootService(settings, session),
            journal=OperationJournal(session),
        ).execute(plan)
        row.status = "completed"
        auto["local_operations_complete"] = True
        auto["local_target_paths"] = [
            str(step.target_path) for step in plan.steps if step.category == "media"
        ]
        payload["local_operations_complete"] = True
        job.payload = redact_payload(payload)
        logger.info(
            "Auto plan executed job_id=%s plan_id=%s steps=%s", job.id, row.plan_id, len(plan.steps)
        )

    def _require_settings(self) -> Settings:
        if self._settings is None:
            raise RuntimeError("worker_settings_required")
        return self._settings

    async def _notify_emby(self, session: Session, job: Job) -> None:
        if not _emby_enabled(session, job):
            return
        if self._emby_client is None:
            raise RuntimeError("emby_client_unconfigured")
        payload = _payload(job)
        rule = _rule_for_job(session, job)
        logger.info("Emby notification started job_id=%s rule_id=%s", job.id, rule.rule_id)
        await self._emby_client.scan_library()
        emby_payload = payload.setdefault("emby", {})
        if not isinstance(emby_payload, dict):
            emby_payload = {}
            payload["emby"] = emby_payload
        target_paths = _auto_payload(payload).get("local_target_paths") or []
        mappings = (rule.emby_options or {}).get("path_mappings") or []
        if target_paths and mappings:
            mapped = EmbyPathMapper(mappings).map_path(Path(str(target_paths[0])))
            emby_payload["mapped_path"] = mapped.emby_path
            item = await self._emby_client.find_item_by_path(mapped.emby_path)
            if item:
                item_id = str(item.get("Id") or item.get("id") or "")
                if item_id:
                    await self._emby_client.refresh_item(item_id)
                    emby_payload["refreshed_item_id"] = item_id
                    logger.info("Emby item refreshed job_id=%s item_id=%s", job.id, item_id)
        emby_payload["notified"] = True
        job.payload = redact_payload(payload)
        logger.info(
            "Emby notification completed job_id=%s mapped_path=%s",
            job.id,
            emby_payload.get("mapped_path"),
        )


def _payload(job: Job) -> dict[str, Any]:
    payload = deepcopy(dict(job.payload or {}))
    if not isinstance(payload.get("auto"), dict):
        payload["auto"] = {}
    return payload


def _auto_payload(payload: dict[str, Any]) -> dict[str, Any]:
    auto = payload.setdefault("auto", {})
    if not isinstance(auto, dict):
        payload["auto"] = {}
        return payload["auto"]
    return auto


def _rule_for_job(session: Session, job: Job) -> WatchRule:
    if not job.rule_id:
        raise RuntimeError("watch_rule_required")
    rule = session.scalar(select(WatchRule).where(WatchRule.rule_id == job.rule_id))
    if rule is None:
        raise RuntimeError("watch_rule_missing")
    return rule


def _organization_mode(value: str) -> OrganizationMode:
    if value == "preview":
        return "copy"
    if value not in {"preview", "in_place", "move", "copy", "hardlink", "symlink"}:
        raise RuntimeError("invalid_organization_mode")
    return cast(OrganizationMode, value)


def _persist_media_item(
    session: Session,
    settings: Settings,
    path: Path,
    *,
    media_identity: str,
) -> MediaItem:
    storage_roots = StorageRootService(settings, session)
    validation = storage_roots.validate_inside_root(path)
    item = _media_scan_item(path, media_identity=media_identity)
    existing = session.scalar(
        select(MediaItem).where(
            (MediaItem.identity == media_identity) | (MediaItem.path == str(path))
        )
    )
    relative_path = str(path.relative_to(Path(validation.root.path)))
    if existing is None:
        existing = MediaItem(
            storage_root_id=validation.root.id,
            path=str(path),
            relative_path=relative_path,
            filename=path.name,
            group_key=item.group_key,
            multipart_index=item.multipart_index,
            identity=media_identity,
            size_bytes=item.size_bytes,
            mtime_ns=item.mtime_ns,
        )
        session.add(existing)
    else:
        existing.storage_root_id = validation.root.id
        existing.path = str(path)
        existing.relative_path = relative_path
        existing.filename = path.name
        existing.group_key = item.group_key
        existing.multipart_index = item.multipart_index
        existing.size_bytes = item.size_bytes
        existing.mtime_ns = item.mtime_ns
    session.flush()
    return existing


def _media_scan_item(path: Path, *, media_identity: str) -> MediaScanItem:
    stat = path.stat()
    return MediaScanItem(
        path=path,
        group_key=path.stem,
        identity=media_identity,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _media_item_payload(item: MediaScanItem) -> dict[str, Any]:
    return {
        **item.model_dump(mode="json"),
        "sidecars": [sidecar.model_dump(mode="json") for sidecar in item.sidecars],
    }


def _media_scan_item_from_payload(payload: dict[str, Any]) -> MediaScanItem:
    material = dict(payload)
    material["sidecars"] = [
        MediaSidecarScanItem.model_validate(sidecar)
        for sidecar in material.get("sidecars", [])
        if isinstance(sidecar, dict)
    ]
    return MediaScanItem.model_validate(material)


def _match_input(path: Path) -> tuple[MatchInput, str]:
    normalized = normalize_filename_for_search(path.name, parent_name=path.parent.name)
    title = normalized.search_text
    if normalized.identifier and title.startswith(normalized.identifier):
        title = title[len(normalized.identifier) :].strip()
    query = title or normalized.search_text
    return (
        MatchInput(
            search_text=query,
            identifier=normalized.identifier,
            title=query,
            parent_hint=normalized.parent_hint,
        ),
        query,
    )


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
    strict_assets_missing: bool,
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
        asset_ready=not strict_assets or not strict_assets_missing,
        unique_detail=True,
    )


def _search_result_from_candidate(row: SearchCandidate | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = row.candidate_json or {}
    result = payload.get("search_result") if isinstance(payload, dict) else None
    return result if isinstance(result, dict) else None


def _decision_payload(decision, *, lead: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"gate_reasons": list(decision.reasons)}
    if decision.selected is not None:
        payload["selected_source_id"] = decision.selected.source_id
    if decision.score is not None:
        payload["score"] = {
            "total": decision.score.total,
            "breakdown": decision.score.breakdown,
            "lead": lead,
        }
    return payload


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


def _emby_enabled(session: Session, job: Job) -> bool:
    rule = _rule_for_job(session, job)
    return bool((rule.emby_options or {}).get("enabled"))


def _include_source_snapshot(session: Session, rule: WatchRule) -> bool:
    option = (rule.metadata_options or {}).get("include_source_snapshot")
    if isinstance(option, bool):
        return option
    defaults = SettingsStore(session).organization_defaults()
    return bool(defaults.get("include_source_snapshot"))
