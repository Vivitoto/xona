from __future__ import annotations

from dataclasses import dataclass

from backend.app.schemas.operations import OperationPlan, OperationStep
from backend.app.services.operation_executor import (
    OperationExecutionError,
    observe_file,
)
from backend.app.services.storage_roots import StorageRootService


@dataclass(frozen=True)
class RollbackResult:
    reversed_steps: tuple[str, ...]


class RollbackRefused(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RollbackService:
    def __init__(self, storage_roots: StorageRootService) -> None:
        self._storage_roots = storage_roots

    def rollback(self, plan: OperationPlan) -> RollbackResult:
        reversed_steps: list[str] = []
        for step in reversed(plan.steps):
            if step.operation == "preview" or not step.target_path.exists():
                continue
            self._verify_target(step)
            try:
                self._storage_roots.validate_inside_root(step.target_path)
                self._storage_roots.validate_inside_root(step.target_path.parent)
                if step.source_path is not None:
                    self._storage_roots.validate_inside_root(step.source_path)
                    self._storage_roots.validate_inside_root(step.source_path.parent)
            except Exception as exc:
                raise RollbackRefused("outside_storage_root") from exc

            if step.operation in {"move", "rename"}:
                if step.source_path is None:
                    raise RollbackRefused("source_missing")
                if step.source_path.exists():
                    raise RollbackRefused("rollback_source_exists")
                step.source_path.parent.mkdir(parents=True, exist_ok=True)
                step.target_path.rename(step.source_path)
            elif step.operation in {"copy", "hardlink", "symlink", "write_generated"}:
                step.target_path.unlink()
            else:
                raise RollbackRefused("unsupported_operation")
            reversed_steps.append(step.step_id)
        return RollbackResult(reversed_steps=tuple(reversed_steps))

    def _verify_target(self, step: OperationStep) -> None:
        try:
            observed = observe_file(step.target_path)
        except OperationExecutionError as exc:
            raise RollbackRefused("target_verification_failed") from exc
        if step.expected_size_bytes is not None and observed.size_bytes != step.expected_size_bytes:
            raise RollbackRefused("target_verification_failed")
        if step.sha256 is not None and observed.sha256 != step.sha256:
            raise RollbackRefused("target_verification_failed")
        if step.mtime_ns is not None and observed.mtime_ns != step.mtime_ns:
            raise RollbackRefused("target_verification_failed")
