from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.db.models import Actor, EmbyLink
from backend.app.integrations.emby import EmbyClient
from backend.app.integrations.flaresolverr import FlareSolverrClient
from backend.app.integrations.xchina import XChinaAdapter
from backend.app.schemas.actors import (
    ActorAliasesUpdate,
    ActorListResponse,
    ActorMergeRequest,
    ActorPortraitResponse,
    ActorRead,
    ActorRefreshResponse,
    ActorSyncEmbyResponse,
    ActorWorksResponse,
)
from backend.app.services.actors import ActorCacheService
from backend.app.services.settings_store import SettingsStore

router = APIRouter(prefix="/api/actors", tags=["actors"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.get("", response_model=ActorListResponse)
async def list_actors(
    request: Request,
    search: str | None = None,
    missing_image: bool = False,
    session: Session = Depends(get_db),
) -> ActorListResponse:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    return ActorListResponse(
        actors=[
            _actor_read(service, actor)
            for actor in service.list_actors(
                search=search,
                missing_image=missing_image,
            )
        ]
    )


@router.get("/{actor_id}", response_model=ActorRead)
async def get_actor(
    actor_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> ActorRead:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    try:
        return _actor_read(service, service.get_actor(actor_id), include_works=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Actor not found") from exc


@router.put("/{actor_id}/aliases", response_model=ActorRead)
async def update_actor_aliases(
    actor_id: int,
    payload: ActorAliasesUpdate,
    request: Request,
    session: Session = Depends(get_db),
) -> ActorRead:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    try:
        actor = service.set_aliases(actor_id, payload.aliases)
        session.commit()
        return _actor_read(service, actor, include_works=True)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc


@router.post("/{actor_id}/merge", response_model=ActorRead)
async def merge_actor(
    actor_id: int,
    payload: ActorMergeRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ActorRead:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    try:
        actor = service.merge(actor_id, payload.duplicate_actor_id)
        session.commit()
        return _actor_read(service, actor, include_works=True)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc


@router.post("/{actor_id}/portrait", response_model=ActorPortraitResponse)
async def replace_actor_portrait(
    actor_id: int,
    request: Request,
    content_type: str = Header(default="application/octet-stream"),
    x_content_sha256: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> ActorPortraitResponse:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    content = await request.body()
    try:
        actor = service.replace_portrait(
            actor_id,
            content,
            content_type=content_type,
            expected_sha256=x_content_sha256,
        )
        session.commit()
        assert actor.portrait_sha256 is not None
        assert actor.portrait_size_bytes is not None
        return ActorPortraitResponse(
            actor=_actor_read(service, actor, include_works=True),
            sha256=actor.portrait_sha256,
            size_bytes=actor.portrait_size_bytes,
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc


@router.post("/{actor_id}/refresh", response_model=ActorRefreshResponse)
async def refresh_actor(
    actor_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> ActorRefreshResponse:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    adapter, closer = _xchina_adapter_for(request, session)
    try:
        actor = await service.refresh_actor(actor_id, adapter)
        session.commit()
        return ActorRefreshResponse(actor=_actor_read(service, actor, include_works=True))
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail=redact_payload({"error": str(exc)}),
        ) from exc
    finally:
        if closer is not None:
            await closer()


@router.get("/{actor_id}/works", response_model=ActorWorksResponse)
async def get_actor_works(
    actor_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> ActorWorksResponse:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    try:
        return ActorWorksResponse(actor_id=actor_id, works=service.linked_works(actor_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Actor not found") from exc


@router.post("/{actor_id}/sync-emby", response_model=ActorSyncEmbyResponse)
async def sync_actor_emby(
    actor_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> ActorSyncEmbyResponse:
    service = ActorCacheService(session, request.app.state.settings.config_dir)
    config = _emby_config(request, session)
    client, closer = _emby_client_for(request, config)
    try:
        actor, uploaded = await service.sync_emby(
            actor_id,
            client,
            upload_portrait=bool(config.get("upload_actor_portraits", True)),
        )
        session.add(
            EmbyLink(
                entity_type="actor",
                entity_id=actor.id,
                actor_id=actor.id,
                emby_person_id=actor.emby_person_id,
                payload={},
            )
        )
        session.commit()
        return ActorSyncEmbyResponse(
            actor=_actor_read(service, actor, include_works=True),
            uploaded_portrait=uploaded,
        )
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail=redact_payload({"error": str(exc)}),
        ) from exc
    finally:
        if closer is not None:
            await closer()


def _actor_read(
    service: ActorCacheService,
    actor: Actor,
    *,
    include_works: bool = False,
) -> ActorRead:
    return ActorRead(
        id=actor.id,
        canonical_name=actor.canonical_name,
        aliases=[alias.alias for alias in actor.aliases],
        source=actor.source,
        source_id=actor.source_id,
        profile_url=actor.profile_url,
        portrait_source_url=actor.portrait_source_url,
        portrait_cache_path=actor.portrait_cache_path,
        portrait_sha256=actor.portrait_sha256,
        portrait_size_bytes=actor.portrait_size_bytes,
        biography=actor.biography,
        profile_fields=dict(actor.profile_fields or {}),
        associated_works=list(actor.associated_works or []),
        emby_person_id=actor.emby_person_id,
        linked_works=service.linked_works(actor.id) if include_works else [],
    )


def _xchina_adapter_for(
    request: Request,
    session: Session,
) -> tuple[Any, Callable[[], Awaitable[None]] | None]:
    adapter = getattr(request.app.state, "xchina_adapter", None)
    if adapter is not None:
        return adapter, None
    settings: Settings = request.app.state.settings
    store_settings = SettingsStore(session).xchina_settings()
    endpoint = settings.flaresolverr_url or store_settings.get("flaresolverr_url")
    if not endpoint:
        raise HTTPException(status_code=400, detail="FlareSolverr URL required")
    flaresolverr = FlareSolverrClient(
        str(endpoint),
        proxy_url=settings.proxy_url or store_settings.get("proxy_url"),
    )
    return XChinaAdapter(flaresolverr, session), flaresolverr.close


def _emby_config(request: Request, session: Session) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    config = SettingsStore(session).emby_settings()
    if settings.emby_server_url:
        config["server_url"] = settings.emby_server_url
    if settings.emby_api_key:
        config["api_key"] = settings.emby_api_key
    injected = getattr(request.app.state, "emby_client", None)
    if injected is not None:
        config.setdefault("server_url", "injected")
        config.setdefault("api_key", "injected")
        config.setdefault("enabled", True)
        return config
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Emby is not enabled")
    if not config.get("server_url") or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Emby server URL and API key required")
    return config


def _emby_client_for(
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
