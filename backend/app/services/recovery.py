from __future__ import annotations

from dataclasses import dataclass

from backend.app.schemas.operations import OperationPlan, OperationStep
from backend.app.services.operation_executor import observe_file, temp_path_for_step


@dataclass(frozen=True)
class RecoveryReport:
    completed: tuple[str, ...] = ()
    partial: tuple[str, ...] = ()
    externally_modified: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()


class RecoveryService:
    @staticmethod
    def temp_path_for_step(plan: OperationPlan, step: OperationStep):
        return temp_path_for_step(plan, step)

    def inspect_plan(self, plan: OperationPlan) -> RecoveryReport:
        completed: list[str] = []
        partial: list[str] = []
        externally_modified: list[str] = []
        pending: list[str] = []
        for step in plan.steps:
            temp_path = temp_path_for_step(plan, step)
            if temp_path.exists() or temp_path.is_symlink():
                partial.append(step.step_id)
                continue
            if not step.target_path.exists():
                pending.append(step.step_id)
                continue
            if _target_matches(step):
                completed.append(step.step_id)
            else:
                externally_modified.append(step.step_id)
        return RecoveryReport(
            completed=tuple(completed),
            partial=tuple(partial),
            externally_modified=tuple(externally_modified),
            pending=tuple(pending),
        )


def _target_matches(step: OperationStep) -> bool:
    try:
        observed = observe_file(step.target_path)
    except Exception:
        return False
    if step.expected_size_bytes is not None and observed.size_bytes != step.expected_size_bytes:
        return False
    if step.sha256 is not None and observed.sha256 != step.sha256:
        return False
    return True
