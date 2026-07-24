from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.integrations.flaresolverr import FlareSolverrClient
from backend.app.integrations.xchina import XChinaAdapter
from backend.app.schemas.manual import (
    ManualExecutePlanRequest,
    ManualExecutePlanResponse,
    ManualJobRead,
    ManualPreviewRequest,
    ManualPreviewResponse,
    ManualScanRequest,
    ManualScanResponse,
    ManualSearchRequest,
    ManualSearchResponse,
    ManualSelectCandidateRequest,
    ManualSelectCandidateResponse,
)
from backend.app.services.manual import ManualOrganizerError, ManualOrganizerService
from backend.app.services.settings_store import SettingsStore

router = APIRouter(prefix="/api/manual", tags=["manual"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.post("/scan", response_model=ManualScanResponse)
async def scan_manual_directory(
    payload: ManualScanRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualScanResponse:
    service, closer = _service_for(request, session)
    try:
        response = service.scan(
            payload.directory,
            recursive=payload.recursive,
            ignore_patterns=payload.ignore_patterns,
        )
        session.commit()
        return response
    except ManualOrganizerError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.post("/search", response_model=ManualSearchResponse)
async def search_manual_candidates(
    payload: ManualSearchRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualSearchResponse:
    service, closer = _service_for(request, session)
    try:
        response = await service.search(
            job_id=payload.job_id,
            filename=payload.filename,
            query=payload.query,
            normalized_query=payload.normalized_query,
        )
        session.commit()
        return response
    except ManualOrganizerError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.post(
    "/jobs/{job_id}/select-candidate",
    response_model=ManualSelectCandidateResponse,
)
async def select_manual_candidate(
    job_id: int,
    payload: ManualSelectCandidateRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualSelectCandidateResponse:
    service, closer = _service_for(request, session)
    try:
        response = await service.select_candidate(
            job_id,
            candidate_id=payload.candidate_id,
            source_url=payload.source_url,
            detail=payload.detail,
            safety=payload.safety,
            strict_assets=payload.strict_assets,
        )
        session.commit()
        return response
    except ManualOrganizerError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.post("/jobs/{job_id}/preview", response_model=ManualPreviewResponse)
async def preview_manual_plan(
    job_id: int,
    payload: ManualPreviewRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualPreviewResponse:
    service, closer = _service_for(request, session)
    try:
        response = await service.preview(job_id, payload)
        session.commit()
        return response
    except ManualOrganizerError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.post("/plans/{plan_id}/execute", response_model=ManualExecutePlanResponse)
async def execute_manual_plan(
    plan_id: str,
    payload: ManualExecutePlanRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualExecutePlanResponse:
    service, closer = _service_for(request, session)
    try:
        response = service.execute_plan(
            plan_id,
            approved=payload.approved,
            plan_version=payload.plan_version,
        )
        session.commit()
        return response
    except ManualOrganizerError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.get("/jobs/{job_id}", response_model=ManualJobRead)
async def get_manual_job(
    job_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualJobRead:
    service, closer = _service_for(request, session)
    try:
        return service.get_job(job_id)
    except ManualOrganizerError as exc:
        raise _http_error(exc) from exc
    finally:
        if closer is not None:
            await closer()


def _service_for(
    request: Request,
    session: Session,
) -> tuple[ManualOrganizerService, Callable[[], Awaitable[None]] | None]:
    settings: Settings = request.app.state.settings
    adapter = getattr(request.app.state, "manual_search_adapter", None)
    if adapter is None:
        adapter = getattr(request.app.state, "xchina_adapter", None)
    if adapter is not None:
        return (
            ManualOrganizerService(
                settings,
                session,
                search_adapter=adapter,
                asset_adapter=adapter,
            ),
            None,
        )
    store_settings = SettingsStore(session).xchina_settings()
    endpoint = settings.flaresolverr_url or store_settings.get("flaresolverr_url")
    if not endpoint:
        return ManualOrganizerService(settings, session), None
    flaresolverr = FlareSolverrClient(
        str(endpoint),
        proxy_url=settings.proxy_url or store_settings.get("proxy_url"),
    )
    xchina = XChinaAdapter(flaresolverr, session)
    return (
        ManualOrganizerService(
            settings,
            session,
            search_adapter=xchina,
            asset_adapter=xchina,
        ),
        flaresolverr.close,
    )


def _http_error(exc: ManualOrganizerError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code or status.HTTP_400_BAD_REQUEST,
        detail=redact_payload({"error": str(exc), "reasons": exc.reasons}),
    )
