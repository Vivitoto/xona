from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.core.settings import Settings
from backend.app.integrations.emby import EmbyPathMapper
from backend.app.integrations.flaresolverr import FlareSolverrClient
from backend.app.integrations.xchina import XChinaAdapter
from backend.app.schemas.settings import (
    AppSettingsRead,
    AppSettingsUpdate,
    FlareSolverrTestRequest,
    FlareSolverrTestResponse,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    XChinaTestRequest,
    XChinaTestResponse,
)
from backend.app.schemas.templates import TemplateContext
from backend.app.services.settings_store import SettingsStore, SettingsUpdateError
from backend.app.services.storage_roots import StorageRootService, StorageRootValidationError
from backend.app.services.templates import preview_template

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.get("", response_model=AppSettingsRead)
async def get_settings(
    request: Request,
    session: Session = Depends(get_db),
) -> AppSettingsRead:
    values = SettingsStore(session).get_app_settings()
    _overlay_runtime_settings(request.app.state.settings, values)
    return AppSettingsRead.model_validate(values)


@router.put("", response_model=AppSettingsRead)
async def update_settings(
    payload: AppSettingsUpdate,
    request: Request,
    session: Session = Depends(get_db),
) -> AppSettingsRead:
    patch = payload.model_dump(mode="json", exclude_unset=True)
    _remove_read_only_runtime_settings(patch)
    settings: Settings = request.app.state.settings
    try:
        _validate_settings_patch(settings, session, patch)
        values = SettingsStore(session).update_app_settings(patch)
        _sync_storage_roots(settings, session, patch)
        session.commit()
    except (SettingsUpdateError, StorageRootValidationError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc
    _overlay_runtime_settings(settings, values)
    return AppSettingsRead.model_validate(values)


@router.post("/flaresolverr/test", response_model=FlareSolverrTestResponse)
async def test_flaresolverr(
    payload: FlareSolverrTestRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> FlareSolverrTestResponse:
    store_settings = SettingsStore(session).xchina_settings()
    settings: Settings = request.app.state.settings
    endpoint = payload.url or settings.flaresolverr_url or store_settings.get("flaresolverr_url")
    proxy_url = payload.proxy_url or settings.proxy_url or store_settings.get("proxy_url")
    if not endpoint:
        raise HTTPException(status_code=400, detail="FlareSolverr URL required")
    client = getattr(request.app.state, "flaresolverr_client", None)
    owns_client = False
    if client is None:
        client = FlareSolverrClient(str(endpoint), proxy_url=proxy_url)
        owns_client = True
    started = time.monotonic()
    try:
        response = await client.request_get(payload.test_url)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        headers = response.headers or {}
        cookie_count = sum(1 for key in headers if key.lower() == "set-cookie")
        return FlareSolverrTestResponse(
            ok=True,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            cloudflare_state="ok",
            cookie_count=cookie_count,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return FlareSolverrTestResponse(
            ok=False,
            status_code=None,
            elapsed_ms=elapsed_ms,
            cloudflare_state="unknown",
            diagnostics={"error": redact_payload(str(exc))},
        )
    finally:
        if owns_client:
            await client.close()


@router.post("/xchina/test", response_model=XChinaTestResponse)
async def test_xchina(
    payload: XChinaTestRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> XChinaTestResponse:
    adapter = getattr(request.app.state, "xchina_adapter", None)
    closer = None
    if adapter is None:
        settings: Settings = request.app.state.settings
        store_settings = SettingsStore(session).xchina_settings()
        endpoint = settings.flaresolverr_url or store_settings.get("flaresolverr_url")
        if not endpoint:
            raise HTTPException(status_code=400, detail="FlareSolverr URL required")
        flaresolverr = FlareSolverrClient(
            str(endpoint),
            proxy_url=settings.proxy_url or store_settings.get("proxy_url"),
        )
        adapter = XChinaAdapter(flaresolverr, session)
        closer = flaresolverr.close
    try:
        results = await adapter.search(payload.query)
        return XChinaTestResponse(ok=True, candidate_count=len(results))
    except Exception as exc:
        return XChinaTestResponse(
            ok=False,
            diagnostics={"error": redact_payload(str(exc))},
        )
    finally:
        if closer is not None:
            await closer()


@router.post("/templates/preview", response_model=TemplatePreviewResponse)
async def preview_templates(payload: TemplatePreviewRequest) -> TemplatePreviewResponse:
    preview = preview_template(
        folder_templates=payload.folder_templates,
        filename_template=payload.filename_template,
        context=TemplateContext.model_validate(payload.context),
    )
    return TemplatePreviewResponse.model_validate(preview.model_dump())


def _overlay_runtime_settings(settings: Settings, values: dict[str, Any]) -> None:
    storage = values.setdefault("storage", {})
    bootstrap_roots = [
        str(path) for path, _source in settings.bootstrap_storage_roots()
    ]
    if bootstrap_roots:
        storage["env_roots"] = bootstrap_roots
        bootstrap_root_set = set(bootstrap_roots)
        storage["roots"] = [
            root for root in storage.get("roots") or [] if root not in bootstrap_root_set
        ]
    xchina = values.setdefault("xchina", {})
    if settings.flaresolverr_url:
        xchina["flaresolverr_url"] = settings.flaresolverr_url
    if settings.proxy_url:
        xchina["proxy_url"] = settings.proxy_url
    emby = values.setdefault("emby", {})
    if settings.emby_server_url:
        emby["server_url"] = settings.emby_server_url
    if settings.emby_api_key:
        emby["api_key"] = "********"
    auth = values.setdefault("auth", {})
    auth["enabled"] = settings.auth_enabled
    if settings.auth_username:
        auth["username"] = settings.auth_username


def _remove_read_only_runtime_settings(patch: dict[str, Any]) -> None:
    storage = patch.get("storage")
    if isinstance(storage, dict):
        storage.pop("env_roots", None)


def _validate_settings_patch(
    settings: Settings,
    session: Session,
    patch: dict[str, Any],
) -> None:
    storage = patch.get("storage")
    if isinstance(storage, dict):
        for root in storage.get("roots") or []:
            root_path = Path(root)
            if "\0" in str(root_path) or not root_path.is_absolute():
                raise ValueError("Storage roots must be absolute safe paths")
            if not root_path.exists() or not root_path.is_dir():
                raise ValueError(f"Storage root is not available: {root_path}")

    emby = patch.get("emby")
    if isinstance(emby, dict):
        mappings = emby.get("path_mappings")
        if mappings is not None:
            mapper = EmbyPathMapper(mappings)
            if not mapper.mappings and emby.get("enabled"):
                raise ValueError("At least one Emby path mapping is required")
            for mapping in mapper.mappings:
                container_root = Path(mapping.container_root)
                if "\0" in str(container_root) or not container_root.is_absolute():
                    raise ValueError("Emby container roots must be absolute safe paths")
                if not mapping.emby_root.strip():
                    raise ValueError("Emby visible roots cannot be empty")

    for section_name in ("xchina", "confidence_safety"):
        section = patch.get(section_name)
        if isinstance(section, dict):
            for key in ("cache_dir",):
                if key in section and section[key] is not None:
                    _validate_cache_dir(settings, Path(section[key]))

    if "storage" in patch:
        StorageRootService(settings, session).reconcile_roots()


def _validate_cache_dir(settings: Settings, path: Path) -> None:
    if "\0" in str(path) or not path.is_absolute():
        raise ValueError("Cache directories must be absolute safe paths")
    try:
        path.resolve(strict=False).relative_to(settings.config_dir.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("Cache directories must remain under config_dir") from exc


def _sync_storage_roots(
    settings: Settings,
    session: Session,
    patch: dict[str, Any],
) -> None:
    storage = patch.get("storage")
    if not isinstance(storage, dict):
        return
    if "roots" not in storage:
        return
    service = StorageRootService(settings, session)
    desired_paths: set[str] = set()
    for root in storage.get("roots") or []:
        added = service.add_root(Path(root))
        desired_paths.add(added.path)

    for root in service.list_roots(include_disabled=True):
        if root.source == "user":
            root.enabled = root.path in desired_paths
