from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.schemas.history import (
    HistoryPlanRead,
    HistoryPlansResponse,
    RollbackResponse,
)
from backend.app.schemas.operations import OperationPlan
from backend.app.services.jobs import InvalidJobTransition, JobService
from backend.app.services.recovery import RecoveryService
from backend.app.services.rollback import RollbackRefused, RollbackService
from backend.app.services.storage_roots import StorageRootService

router = APIRouter(prefix="/api", tags=["history"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.get("/history/plans", response_model=HistoryPlansResponse)
async def list_history_plans(
    session: Session = Depends(get_db),
) -> HistoryPlansResponse:
    rows = list(
        session.scalars(
            select(OperationPlanModel).order_by(
                OperationPlanModel.created_at.desc(),
                OperationPlanModel.id.desc(),
            )
        )
    )
    return HistoryPlansResponse(plans=[_history_plan(row) for row in rows])


@router.post("/plans/{plan_id}/rollback", response_model=RollbackResponse)
async def rollback_plan(
    plan_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> RollbackResponse:
    row = session.scalar(
        select(OperationPlanModel).where(OperationPlanModel.plan_id == plan_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = _operation_plan(row)
    settings: Settings = request.app.state.settings
    storage_roots = StorageRootService(settings, session)
    try:
        result = RollbackService(storage_roots).rollback(plan)
    except RollbackRefused as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "rollback_refused", "reason": exc.reason},
        ) from exc
    row.status = "rolled_back"
    if row.job_id is not None:
        try:
            JobService(session).transition_job(
                row.job_id,
                "rolled_back",
                payload={"plan_id": plan_id},
            )
        except (ValueError, InvalidJobTransition):
            pass
    session.commit()
    return RollbackResponse(
        plan_id=plan_id,
        status=row.status,
        reversed_steps=list(result.reversed_steps),
    )


def _history_plan(row: OperationPlanModel) -> HistoryPlanRead:
    plan = _operation_plan(row)
    report = RecoveryService().inspect_plan(plan)
    if report.externally_modified:
        verification = "externally_modified"
    elif report.partial:
        verification = "partial"
    elif report.pending:
        verification = "pending"
    else:
        verification = "verified"
    return HistoryPlanRead(
        plan_id=row.plan_id,
        job_id=row.job_id,
        mode=row.mode,
        status=row.status,
        verification_status=verification,
        target_paths=[str(step.target_path) for step in plan.steps],
        created_at=row.created_at,
    )


def _operation_plan(row: OperationPlanModel) -> OperationPlan:
    return OperationPlan.model_validate(row.plan_json).model_copy(
        update={"database_id": row.id}
    )
