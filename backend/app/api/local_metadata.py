from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.schemas.local_metadata import (
    LocalAnalyzeRequest,
    LocalAnalyzeResponse,
    LocalCacheCleanupRequest,
    LocalCacheCleanupResponse,
    LocalCoverPreviewRequest,
    LocalCoverPreviewResponse,
    LocalExecutePlanRequest,
    LocalExecutePlanResponse,
    LocalFrameRequest,
    LocalFrameResponse,
    LocalMetadataBatchCreateRequest,
    LocalMetadataBatchListResponse,
    LocalMetadataBatchRead,
    LocalMetadataBatchSummary,
    LocalNfoPreviewRequest,
    LocalNfoPreviewResponse,
    LocalPlanPreviewRequest,
    LocalPlanPreviewResponse,
    LocalScanRequest,
    LocalScanResponse,
)
from backend.app.services.local_metadata_batches import (
    LocalMetadataBatchError,
    LocalMetadataBatchManager,
    LocalMetadataBatchService,
    batch_read,
    batch_summary,
    recalculate_batch_counts,
)
from backend.app.services.local_metadata import LocalMetadataError, LocalMetadataService

router = APIRouter(prefix="/api/local-metadata", tags=["local-metadata"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.post("/scan", response_model=LocalScanResponse)
async def scan_unmatched_directory(
    payload: LocalScanRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalScanResponse:
    service = _service_for(request, session)
    try:
        response = service.scan(payload)
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post("/batches", response_model=LocalMetadataBatchRead)
async def create_local_metadata_batch(
    payload: LocalMetadataBatchCreateRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalMetadataBatchRead:
    manager = _batch_manager_for(request)
    service = LocalMetadataBatchService(session)
    try:
        batch = service.create_batch(payload)
        session.commit()
        manager.start_preview(batch.batch_id)
        return batch_read(batch)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.get("/batches", response_model=LocalMetadataBatchListResponse)
async def list_local_metadata_batches(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> LocalMetadataBatchListResponse:
    try:
        return LocalMetadataBatchService(session).list_batches(limit=limit)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.get("/batches/{batch_id}/summary", response_model=LocalMetadataBatchSummary)
async def get_local_metadata_batch_summary(
    batch_id: str,
    session: Session = Depends(get_db),
) -> LocalMetadataBatchSummary:
    try:
        batch = LocalMetadataBatchService(session).get_batch(batch_id)
        return batch_summary(batch)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.get("/batches/{batch_id}", response_model=LocalMetadataBatchRead)
async def get_local_metadata_batch(
    batch_id: str,
    session: Session = Depends(get_db),
) -> LocalMetadataBatchRead:
    try:
        batch = LocalMetadataBatchService(session).get_batch(batch_id)
        return batch_read(batch)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.post("/batches/{batch_id}/cancel", response_model=LocalMetadataBatchRead)
async def cancel_local_metadata_batch(
    batch_id: str,
    session: Session = Depends(get_db),
) -> LocalMetadataBatchRead:
    try:
        batch = LocalMetadataBatchService(session).cancel_batch(batch_id)
        session.commit()
        return batch_read(batch)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.post("/batches/{batch_id}/retry-failed", response_model=LocalMetadataBatchRead)
async def retry_failed_local_metadata_batch_items(
    batch_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalMetadataBatchRead:
    manager = _batch_manager_for(request)
    try:
        batch, retry_preview, retry_execute = LocalMetadataBatchService(
            session
        ).retry_failed(batch_id)
        session.commit()
        if retry_preview:
            manager.start_preview(batch.batch_id)
        elif retry_execute:
            manager.start_execute(batch.batch_id)
        return batch_read(batch)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.post("/batches/{batch_id}/execute", response_model=LocalMetadataBatchRead)
async def execute_local_metadata_batch(
    batch_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalMetadataBatchRead:
    manager = _batch_manager_for(request)
    try:
        batch = LocalMetadataBatchService(session).get_batch(batch_id)
        recalculate_batch_counts(batch)
        if batch.pending_count or batch.running_count:
            raise LocalMetadataBatchError(
                "batch_not_ready_to_execute",
                status_code=409,
            )
        if batch.executable_count == 0:
            raise LocalMetadataBatchError(
                "batch_has_no_executable_items",
                status_code=409,
            )
        batch.status = "running"
        session.commit()
        manager.start_execute(batch.batch_id)
        return batch_read(batch)
    except LocalMetadataBatchError as exc:
        raise _local_metadata_batch_error(session, exc) from exc


@router.post("/analyze", response_model=LocalAnalyzeResponse)
async def analyze_local_video(
    payload: LocalAnalyzeRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalAnalyzeResponse:
    service = _service_for(request, session)
    try:
        response = service.analyze(payload)
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post("/frames", response_model=LocalFrameResponse)
async def generate_local_frames(
    payload: LocalFrameRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalFrameResponse:
    service = _service_for(request, session)
    try:
        response = service.generate_frames(payload)
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post("/cover-preview", response_model=LocalCoverPreviewResponse)
async def preview_local_cover(
    payload: LocalCoverPreviewRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalCoverPreviewResponse:
    service = _service_for(request, session)
    try:
        response = service.cover_preview(payload)
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post("/nfo-preview", response_model=LocalNfoPreviewResponse)
async def preview_local_nfo(
    payload: LocalNfoPreviewRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalNfoPreviewResponse:
    service = _service_for(request, session)
    try:
        response = service.nfo_preview(payload.metadata)
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post("/preview-plan", response_model=LocalPlanPreviewResponse)
async def preview_local_plan(
    payload: LocalPlanPreviewRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalPlanPreviewResponse:
    service = _service_for(request, session)
    try:
        response = service.preview_plan(payload)
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post("/plans/{plan_id}/execute", response_model=LocalExecutePlanResponse)
async def execute_local_plan(
    plan_id: str,
    payload: LocalExecutePlanRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalExecutePlanResponse:
    service = _service_for(request, session)
    try:
        response = service.execute_plan(
            plan_id,
            approved=payload.approved,
            plan_version=payload.plan_version,
        )
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.post(
    "/plans/{plan_id}/cleanup-cache",
    response_model=LocalCacheCleanupResponse,
)
async def cleanup_local_plan_cache(
    plan_id: str,
    payload: LocalCacheCleanupRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LocalCacheCleanupResponse:
    service = _service_for(request, session)
    try:
        response = service.cleanup_plan_cache(
            plan_id,
            plan_version=payload.plan_version,
        )
        session.commit()
        return response
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc


@router.get("/cache/{asset_id:path}")
async def read_local_cache_asset(
    asset_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> Response:
    service = _service_for(request, session)
    try:
        path = service.cache_path_for_ref(asset_id)
    except LocalMetadataError as exc:
        raise _local_metadata_error(session, exc) from exc
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(
        content=path.read_bytes(),
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


def _service_for(request: Request, session: Session) -> LocalMetadataService:
    settings: Settings = request.app.state.settings
    return LocalMetadataService(settings, session)


def _batch_manager_for(request: Request) -> LocalMetadataBatchManager:
    manager = getattr(request.app.state, "local_metadata_batch_manager", None)
    if not isinstance(manager, LocalMetadataBatchManager):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "batch_manager_unavailable",
                "reasons": ["batch_manager_unavailable"],
            },
        )
    return manager


def _local_metadata_error(session: Session, exc: LocalMetadataError) -> HTTPException:
    session.rollback()
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "reasons": exc.reasons},
    )


def _local_metadata_batch_error(
    session: Session,
    exc: LocalMetadataBatchError,
) -> HTTPException:
    session.rollback()
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "reasons": exc.reasons},
    )
