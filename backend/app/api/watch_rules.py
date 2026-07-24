from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.schemas.watch_rules import (
    ScanNowResponse,
    WatchRuleCreate,
    WatchRuleList,
    WatchRuleRead,
    WatchRuleUpdate,
)
from backend.app.services.watch_rules import WatchRuleService, WatchRuleValidationError

router = APIRouter(prefix="/api", tags=["watch-rules"])
logger = logging.getLogger(__name__)


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


def _service_for(request: Request, session: Session) -> WatchRuleService:
    settings: Settings = request.app.state.settings
    return WatchRuleService(settings, session)


@router.get("/watch-rules", response_model=WatchRuleList)
async def list_watch_rules(
    request: Request,
    session: Session = Depends(get_db),
) -> WatchRuleList:
    service = _service_for(request, session)
    rules = service.list_rules()
    logger.info("Watch rules listed count=%s", len(rules))
    return WatchRuleList(
        rules=[WatchRuleRead.model_validate(rule) for rule in rules]
    )


@router.post(
    "/watch-rules",
    response_model=WatchRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_watch_rule(
    payload: WatchRuleCreate,
    request: Request,
    session: Session = Depends(get_db),
) -> WatchRuleRead:
    service = _service_for(request, session)
    try:
        logger.info(
            "Watch rule create requested source=%s destination=%s enabled=%s realtime=%s",
            payload.source_directory,
            payload.destination_directory,
            payload.enabled,
            payload.realtime,
        )
        rule = service.create_rule(payload)
        session.commit()
    except WatchRuleValidationError as exc:
        logger.warning("Watch rule create rejected error=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Watch rule created rule_id=%s source=%s", rule.rule_id, rule.source_directory)
    return WatchRuleRead.model_validate(rule)


@router.put("/watch-rules/{rule_id}", response_model=WatchRuleRead)
async def update_watch_rule(
    rule_id: str,
    payload: WatchRuleUpdate,
    request: Request,
    session: Session = Depends(get_db),
) -> WatchRuleRead:
    service = _service_for(request, session)
    try:
        logger.info("Watch rule update requested rule_id=%s fields=%s", rule_id, sorted(payload.model_dump(exclude_unset=True).keys()))
        rule = service.update_rule(rule_id, payload)
        session.commit()
    except WatchRuleValidationError as exc:
        logger.warning("Watch rule update rejected rule_id=%s error=%s", rule_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Watch rule updated rule_id=%s enabled=%s", rule.rule_id, rule.enabled)
    return WatchRuleRead.model_validate(rule)


@router.delete("/watch-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watch_rule(
    rule_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> Response:
    service = _service_for(request, session)
    try:
        logger.info("Watch rule delete requested rule_id=%s", rule_id)
        service.delete_rule(rule_id)
        session.commit()
    except WatchRuleValidationError as exc:
        logger.warning("Watch rule delete rejected rule_id=%s error=%s", rule_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Watch rule deleted rule_id=%s", rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/watch-rules/{rule_id}/scan-now", response_model=ScanNowResponse)
async def scan_watch_rule_now(
    rule_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> ScanNowResponse:
    service = _service_for(request, session)
    try:
        logger.info("Watch rule scan-now requested rule_id=%s", rule_id)
        jobs = service.scan_now(rule_id)
        session.commit()
    except WatchRuleValidationError as exc:
        logger.warning("Watch rule scan-now rejected rule_id=%s error=%s", rule_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Watch rule scan-now completed rule_id=%s enqueued_jobs=%s", rule_id, [job.id for job in jobs])
    return ScanNowResponse(rule_id=rule_id, enqueued_jobs=[job.id for job in jobs])
