from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
IMAGE_PROXY_ALLOWED_HOSTS = {
    "www.xchina.co",
    "xchina.co",
    "img.xchina.download",
    "upload.xchina.io",
}
IMAGE_PROXY_MAX_BYTES = 10 * 1024 * 1024


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


@router.get("/image-proxy")
async def proxy_manual_image(
    request: Request,
    url: str = Query(..., min_length=1),
    session: Session = Depends(get_db),
) -> Response:
    _validate_image_proxy_url(url)
    adapter, closer = _asset_adapter_for(request, session)
    if adapter is None:
        raise HTTPException(status_code=400, detail="FlareSolverr URL required")
    try:
        fetched = await adapter.fetch_asset(url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=redact_payload({"error": str(exc)}),
        ) from exc
    finally:
        if closer is not None:
            await closer()

    content_type = fetched.content_type.split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image content type")
    if len(fetched.content) > IMAGE_PROXY_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large")
    return Response(
        content=fetched.content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


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


def _asset_adapter_for(
    request: Request,
    session: Session,
):
    settings: Settings = request.app.state.settings
    adapter = getattr(request.app.state, "manual_search_adapter", None)
    if adapter is None:
        adapter = getattr(request.app.state, "xchina_adapter", None)
    if adapter is not None:
        return adapter, None
    store_settings = SettingsStore(session).xchina_settings()
    endpoint = settings.flaresolverr_url or store_settings.get("flaresolverr_url")
    if not endpoint:
        return None, None
    flaresolverr = FlareSolverrClient(
        str(endpoint),
        proxy_url=settings.proxy_url or store_settings.get("proxy_url"),
    )
    return XChinaAdapter(flaresolverr, session), flaresolverr.close


def _validate_image_proxy_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image URL")
    hostname = parsed.hostname.lower()
    if hostname not in IMAGE_PROXY_ALLOWED_HOSTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image host")


def _http_error(exc: ManualOrganizerError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code or status.HTTP_400_BAD_REQUEST,
        detail=redact_payload({"error": str(exc), "reasons": exc.reasons}),
    )
