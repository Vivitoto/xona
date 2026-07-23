from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.schemas.storage_roots import (
    BrowseResponse,
    StorageRootCreate,
    StorageRootList,
    StorageRootRead,
    StorageRootUpdate,
    ValidatePathRequest,
    ValidatePathResponse,
)
from backend.app.services.storage_roots import StorageRootService, StorageRootValidationError

router = APIRouter(prefix="/api", tags=["storage-roots"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


def _service_for(request: Request, session: Session) -> StorageRootService:
    settings: Settings = request.app.state.settings
    return StorageRootService(settings, session)


@router.get("/storage-roots", response_model=StorageRootList)
async def list_roots(request: Request, session: Session = Depends(get_db)) -> StorageRootList:
    service = _service_for(request, session)
    return StorageRootList(roots=[StorageRootRead.model_validate(root) for root in service.list_roots()])


@router.post("/storage-roots", response_model=StorageRootRead, status_code=status.HTTP_201_CREATED)
async def create_root(
    payload: StorageRootCreate,
    request: Request,
    session: Session = Depends(get_db),
) -> StorageRootRead:
    service = _service_for(request, session)
    try:
        root = service.add_root(payload.path)
        session.commit()
    except StorageRootValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageRootRead.model_validate(root)


@router.get("/storage-roots/browse", response_model=BrowseResponse)
async def browse_root(
    root_id: int,
    request: Request,
    path: str = "",
    session: Session = Depends(get_db),
) -> BrowseResponse:
    service = _service_for(request, session)
    try:
        roots = {root.id: root for root in service.list_roots()}
        root = roots[root_id]
        entries = service.browse(root_id, path)
    except (KeyError, StorageRootValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BrowseResponse(root=StorageRootRead.model_validate(root), entries=entries)


@router.post("/storage-roots/validate", response_model=ValidatePathResponse)
async def validate_path(
    payload: ValidatePathRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ValidatePathResponse:
    service = _service_for(request, session)
    try:
        validation = service.validate_inside_root(payload.path)
    except StorageRootValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ValidatePathResponse(
        inside_root=True,
        root_id=validation.root.id,
        relative_path=validation.relative_path,
    )


@router.put("/storage-roots/{root_id}", response_model=StorageRootRead)
async def update_root(
    root_id: int,
    payload: StorageRootUpdate,
    request: Request,
    session: Session = Depends(get_db),
) -> StorageRootRead:
    service = _service_for(request, session)
    try:
        root = service.update_root(root_id, path=payload.path, enabled=payload.enabled)
        session.commit()
    except StorageRootValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageRootRead.model_validate(root)


@router.delete("/storage-roots/{root_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_root(
    root_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> Response:
    service = _service_for(request, session)
    try:
        service.delete_root(root_id)
        session.commit()
    except StorageRootValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
