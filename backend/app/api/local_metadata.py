from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.schemas.local_metadata import (
    LocalAnalyzeRequest,
    LocalAnalyzeResponse,
    LocalCoverPreviewRequest,
    LocalCoverPreviewResponse,
    LocalExecutePlanRequest,
    LocalExecutePlanResponse,
    LocalFrameRequest,
    LocalFrameResponse,
    LocalNfoPreviewRequest,
    LocalNfoPreviewResponse,
    LocalPlanPreviewRequest,
    LocalPlanPreviewResponse,
    LocalScanRequest,
    LocalScanResponse,
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


def _local_metadata_error(session: Session, exc: LocalMetadataError) -> HTTPException:
    session.rollback()
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "reasons": exc.reasons},
    )
