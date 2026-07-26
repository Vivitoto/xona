from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.integrations.assets import normalize_content_type, normalize_fetched_asset
from backend.app.integrations.flaresolverr import FlareSolverrClient
from backend.app.integrations.xchina import XChinaAdapter
from backend.app.integrations.xchina_config import (
    is_allowed_xchina_resource_url,
    xchina_base_url,
    xchina_max_search_pages,
)
from backend.app.schemas.manual import (
    ManualExecutePlanRequest,
    ManualExecutePlanResponse,
    ManualJobRead,
    ManualOrganizeRequest,
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
    service, closer = await _service_for(request, session)
    try:
        response = service.scan(
            payload.directory,
            recursive=payload.recursive,
            ignore_patterns=payload.ignore_patterns,
        )
        session.commit()
        return response
    except ManualOrganizerError as exc:
        raise _manual_error(session, exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.post("/search", response_model=ManualSearchResponse)
async def search_manual_candidates(
    payload: ManualSearchRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualSearchResponse:
    service, closer = await _service_for(request, session)
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
        raise _manual_error(session, exc) from exc
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
    service, closer = await _service_for(request, session)
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
        raise _manual_error(session, exc) from exc
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
    service, closer = await _service_for(request, session)
    try:
        response = await service.preview(job_id, payload)
        session.commit()
        return response
    except ManualOrganizerError as exc:
        raise _manual_error(session, exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.post("/jobs/{job_id}/organize", response_model=ManualExecutePlanResponse)
async def organize_manual_job(
    job_id: int,
    payload: ManualOrganizeRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualExecutePlanResponse:
    service, closer = await _service_for(request, session)
    try:
        response = await service.organize(job_id, payload)
        session.commit()
        return response
    except ManualOrganizerError as exc:
        raise _manual_error(session, exc) from exc
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
    service, closer = await _service_for(request, session)
    try:
        response = service.execute_plan(
            plan_id,
            approved=payload.approved,
            plan_version=payload.plan_version,
        )
        session.commit()
        return response
    except ManualOrganizerError as exc:
        raise _manual_error(session, exc) from exc
    finally:
        if closer is not None:
            await closer()


@router.get("/jobs/{job_id}", response_model=ManualJobRead)
async def get_manual_job(
    job_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> ManualJobRead:
    service, closer = await _service_for(request, session)
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
    store_settings = SettingsStore(session).xchina_settings()
    _validate_image_proxy_url(url, store_settings)
    adapter, closer = await _asset_adapter_for(request, session)
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

    fetched = normalize_fetched_asset(fetched, fallback_url=url)
    content_type = normalize_content_type(fetched.content_type)
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image content type",
        )
    if len(fetched.content) > IMAGE_PROXY_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large"
        )
    return Response(
        content=fetched.content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


async def _service_for(
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
    flaresolverr = await _shared_flaresolverr_client(
        request,
        str(endpoint),
        settings.proxy_url or store_settings.get("proxy_url"),
    )
    xchina = XChinaAdapter(
        flaresolverr,
        session,
        base_url=xchina_base_url(store_settings),
        max_search_pages=xchina_max_search_pages(store_settings),
    )
    return (
        ManualOrganizerService(
            settings,
            session,
            search_adapter=xchina,
            asset_adapter=xchina,
        ),
        None,
    )


async def _asset_adapter_for(
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
    flaresolverr = await _shared_flaresolverr_client(
        request,
        str(endpoint),
        settings.proxy_url or store_settings.get("proxy_url"),
    )
    return (
        XChinaAdapter(
            flaresolverr,
            session,
            base_url=xchina_base_url(store_settings),
            max_search_pages=xchina_max_search_pages(store_settings),
        ),
        None,
    )


async def _shared_flaresolverr_client(
    request: Request,
    endpoint: str,
    proxy_url: object | None,
) -> FlareSolverrClient:
    key = (endpoint, str(proxy_url or ""))
    current_key = getattr(request.app.state, "xchina_flaresolverr_client_key", None)
    client = getattr(request.app.state, "xchina_flaresolverr_client", None)
    if client is None or current_key != key:
        if client is not None:
            await client.close()
        client = FlareSolverrClient(endpoint, proxy_url=str(proxy_url) if proxy_url else None)
        request.app.state.xchina_flaresolverr_client = client
        request.app.state.xchina_flaresolverr_client_key = key
    return client


async def close_shared_flaresolverr_client(app_state: object) -> None:
    client = getattr(app_state, "xchina_flaresolverr_client", None)
    setattr(app_state, "xchina_flaresolverr_client", None)
    setattr(app_state, "xchina_flaresolverr_client_key", None)
    if client is not None:
        await client.close()


def _validate_image_proxy_url(url: str, store_settings: dict[str, object]) -> None:
    if not is_allowed_xchina_resource_url(url, store_settings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image host"
        )


def _manual_error(session: Session, exc: ManualOrganizerError) -> HTTPException:
    if exc.rollback:
        session.rollback()
    else:
        session.commit()
    return _http_error(exc)


def _http_error(exc: ManualOrganizerError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code or status.HTTP_400_BAD_REQUEST,
        detail=redact_payload({"error": str(exc), "reasons": exc.reasons}),
    )
