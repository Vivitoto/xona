from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.api.manual import (
    IMAGE_PROXY_MAX_BYTES,
    _asset_adapter_for as _manual_asset_adapter_for,
    _shared_flaresolverr_client,
    _validate_image_proxy_url,
    _xchina_settings_snapshot,
)
from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.integrations.assets import normalize_content_type, normalize_fetched_asset
from backend.app.integrations.xchina import XChinaAdapter
from backend.app.integrations.xchina_config import (
    is_allowed_xchina_detail_url,
    xchina_base_url,
    xchina_max_search_pages,
)
from backend.app.schemas.source import SourceSearchResult, SourceVideoDetail
from backend.app.schemas.xchina_search import (
    XChinaDetailRequest,
    XChinaDetailResponse,
    XChinaSearchCandidate,
    XChinaSearchRequest,
    XChinaSearchResponse,
)
from backend.app.services.metadata import normalize_source_video
from backend.app.services.settings_store import SettingsStore

router = APIRouter(prefix="/api/xchina", tags=["xchina"])


class XChinaMetadataAdapter(Protocol):
    async def search(self, query: str) -> list[SourceSearchResult]: ...

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail: ...


class XChinaAssetAdapter(Protocol):
    async def fetch_asset(self, url: str) -> object: ...


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.post("/search", response_model=XChinaSearchResponse)
async def search_xchina_metadata(
    payload: XChinaSearchRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> XChinaSearchResponse:
    query = _required_text(payload.query, field_name="query")
    search_text = _optional_text(payload.normalized_query) or query
    store_settings = _store_settings(session)
    adapter = await _metadata_adapter_for(request, session, store_settings)
    try:
        results = await adapter.search(search_text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=redact_payload(
                {"error": "search_source_unavailable", "message": str(exc)}
            ),
        ) from exc
    return XChinaSearchResponse(
        query=query,
        normalized_query=search_text,
        candidates=[_candidate_from_result(result) for result in results],
    )


@router.post("/detail", response_model=XChinaDetailResponse)
async def fetch_xchina_detail(
    payload: XChinaDetailRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> XChinaDetailResponse:
    source_url = _required_text(payload.source_url, field_name="source_url")
    store_settings = _store_settings(session)
    _validate_detail_url(source_url, store_settings)
    if payload.detail is None:
        adapter = await _metadata_adapter_for(request, session, store_settings)
        try:
            detail = await adapter.fetch_video_detail(source_url)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=redact_payload(
                    {"error": "candidate_detail_unavailable", "message": str(exc)}
                ),
            ) from exc
    else:
        detail = payload.detail.model_copy(update={"source_url": source_url})
    metadata = normalize_source_video(detail)
    return XChinaDetailResponse(source_url=source_url, detail=detail, metadata=metadata)


@router.get("/image-proxy")
async def proxy_xchina_image(
    request: Request,
    url: str = Query(..., min_length=1),
) -> Response:
    store_settings = _xchina_settings_snapshot(request)
    _validate_image_proxy_url(url, store_settings)
    adapter, closer = await _xchina_asset_adapter_for(request, store_settings)
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


async def _metadata_adapter_for(
    request: Request,
    session: Session,
    store_settings: dict[str, object],
) -> XChinaMetadataAdapter:
    state_adapter = _state_adapter(request)
    if state_adapter is not None:
        return state_adapter

    settings: Settings = request.app.state.settings
    endpoint = settings.flaresolverr_url or store_settings.get("flaresolverr_url")
    if not endpoint:
        raise HTTPException(status_code=400, detail="FlareSolverr URL required")
    flaresolverr = await _shared_flaresolverr_client(
        request,
        str(endpoint),
        settings.proxy_url or store_settings.get("proxy_url"),
    )
    try:
        base_url = xchina_base_url(store_settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=redact_payload(str(exc))
        ) from exc
    return XChinaAdapter(
        flaresolverr,
        session,
        base_url=base_url,
        max_search_pages=xchina_max_search_pages(store_settings),
    )


async def _xchina_asset_adapter_for(
    request: Request,
    store_settings: dict[str, object],
):
    state_adapter = _state_asset_adapter(request)
    if state_adapter is not None:
        return state_adapter, None
    return await _manual_asset_adapter_for(request, store_settings)


def _state_adapter(request: Request) -> XChinaMetadataAdapter | None:
    adapter = getattr(request.app.state, "xchina_search_adapter", None)
    if adapter is not None:
        return adapter
    adapter = getattr(request.app.state, "xchina_adapter", None)
    if adapter is not None:
        return adapter
    return None


def _state_asset_adapter(request: Request) -> XChinaAssetAdapter | None:
    adapter = getattr(request.app.state, "xchina_asset_adapter", None)
    if adapter is not None:
        return adapter
    adapter = getattr(request.app.state, "xchina_adapter", None)
    if adapter is not None and hasattr(adapter, "fetch_asset"):
        return adapter
    return None


def _store_settings(session: Session) -> dict[str, object]:
    return dict(SettingsStore(session).xchina_settings())


def _validate_detail_url(url: str, store_settings: dict[str, object]) -> None:
    if not is_allowed_xchina_detail_url(url, store_settings):
        raise HTTPException(
            status_code=400,
            detail="XChina detail URL must be an on-site /videos page",
        )


def _candidate_from_result(result: SourceSearchResult) -> XChinaSearchCandidate:
    return XChinaSearchCandidate(
        source=result.source,
        source_candidate_id=result.source_candidate_id,
        title=result.title,
        image_url=result.thumbnail_url,
        actors=[actor.name for actor in result.actors],
        studio=result.studio,
        series=result.series,
        release_date=result.release_date,
        url=result.url,
    )


def _required_text(value: str, *, field_name: str) -> str:
    cleaned = _optional_text(value)
    if cleaned is None:
        raise HTTPException(status_code=422, detail=f"{field_name} is required")
    return cleaned


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
