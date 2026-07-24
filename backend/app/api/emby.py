from __future__ import annotations

import logging
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
logger = logging.getLogger(__name__)


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
        logger.info("Emby connection test started server=%s", config.get("server_url"))
        result = await client.test_connection()
        logger.info(
            "Emby connection test completed ok=%s server=%s",
            bool(result.get("ok", True)) if isinstance(result, dict) else True,
            config.get("server_url"),
        )
        return EmbyConnectionResponse.model_validate(redact_payload(result))
    except Exception as exc:
        logger.warning(
            "Emby connection test failed server=%s error=%s",
            config.get("server_url"),
            redact_payload(str(exc)),
        )
        raise
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
        logger.info("Emby libraries requested server=%s", config.get("server_url"))
        libraries = await client.libraries()
        logger.info("Emby libraries loaded count=%s", len(libraries))
        return EmbyLibrariesResponse(libraries=libraries)
    except EmbyError as exc:
        logger.warning("Emby libraries failed error=%s", redact_payload(str(exc)))
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
        logger.info("Emby retry requested job_id=%s", job_id)
        job = service.retry_emby(job_id)
        session.commit()
    except (ValueError, InvalidJobTransition) as exc:
        session.rollback()
        logger.warning("Emby retry rejected job_id=%s error=%s", job_id, redact_payload(str(exc)))
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc
    logger.info("Emby retry scheduled job_id=%s state=%s", job.id, job.state)
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
        logger.warning("Emby config rejected reason=server_url_or_api_key_required")
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
