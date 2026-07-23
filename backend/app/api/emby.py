from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.integrations.emby import EmbyClient, EmbyError
from backend.app.schemas.emby import (
    EmbyConnectionResponse,
    EmbyLibrariesResponse,
    EmbyRetryResponse,
    EmbyTestRequest,
)
from backend.app.services.jobs import InvalidJobTransition, JobService
from backend.app.services.settings_store import SettingsStore

router = APIRouter(prefix="/api", tags=["emby"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.post("/emby/test", response_model=EmbyConnectionResponse)
async def test_emby_connection(
    payload: EmbyTestRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> EmbyConnectionResponse:
    config = _emby_config(request, session, overrides=payload.model_dump(exclude_none=True))
    client, closer = _client_for(request, config)
    try:
        result = await client.test_connection()
        return EmbyConnectionResponse.model_validate(redact_payload(result))
    finally:
        if closer is not None:
            await closer()


@router.get("/emby/libraries", response_model=EmbyLibrariesResponse)
async def list_emby_libraries(
    request: Request,
    session: Session = Depends(get_db),
) -> EmbyLibrariesResponse:
    config = _emby_config(request, session)
    client, closer = _client_for(request, config)
    try:
        return EmbyLibrariesResponse(libraries=await client.libraries())
    except EmbyError as exc:
        raise HTTPException(status_code=502, detail=redact_payload(str(exc))) from exc
    finally:
        if closer is not None:
            await closer()


@router.post("/jobs/{job_id}/retry-emby", response_model=EmbyRetryResponse)
async def retry_emby_phase(
    job_id: int,
    session: Session = Depends(get_db),
) -> EmbyRetryResponse:
    service = JobService(session)
    try:
        job = service.retry_emby(job_id)
        session.commit()
    except (ValueError, InvalidJobTransition) as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc
    return EmbyRetryResponse(job_id=job.id, state=job.state)


def _emby_config(
    request: Request,
    session: Session,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    config = SettingsStore(session).emby_settings()
    if settings.emby_server_url:
        config["server_url"] = settings.emby_server_url
    if settings.emby_api_key:
        config["api_key"] = settings.emby_api_key
    for key, value in (overrides or {}).items():
        if value is not None:
            config[key] = value
    if not config.get("server_url") or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Emby server URL and API key required")
    return config


def _client_for(
    request: Request,
    config: dict[str, Any],
) -> tuple[Any, Callable[[], Awaitable[None]] | None]:
    injected = getattr(request.app.state, "emby_client", None)
    if injected is not None:
        return injected, None
    factory = getattr(request.app.state, "emby_client_factory", None)
    if callable(factory):
        return factory(config), None
    client = EmbyClient(str(config["server_url"]), str(config["api_key"]))
    return client, client.close
