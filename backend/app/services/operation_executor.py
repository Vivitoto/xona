from __future__ import annotations

import errno
import hashlib
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.db.models import OperationStep as OperationStepModel
from backend.app.schemas.operations import OperationPlan, OperationStep
from backend.app.services.storage_roots import (
    StorageRootService,
    StorageRootValidationError,
)

logger = logging.getLogger(__name__)


EXECUTION_ERROR_LABELS: dict[str, str] = {
    "target_exists": "目标路径已存在文件",
    "source_missing": "源文件丢失",
    "temp_path_exists": "临时文件冲突（上次整理可能中断，请清理后重试）",
    "target_integrity_mismatch": "复制后文件校验不匹配（磁盘可能存在问题）",
    "source_integrity_mismatch": "源文件在执行中被修改",
    "copy_failed": "文件复制失败（磁盘空间或权限问题）",
    "move_failed": "文件移动失败",
    "finalize_failed": "文件定案失败",
    "hardlink_failed": "硬链接创建失败",
    "symlink_failed": "软链接创建失败",
    "write_generated_failed": "写入 NFO/封面失败（磁盘空间不足）",
    "target_parent_unavailable": "目标目录不可访问",
    "outside_storage_root": "路径超出存储根目录",
    "symlink_ancestor": "路径包含符号链接",
    "target_missing": "操作后目标文件不存在",
    "unsupported_operation": "不支持的操作类型",
}


class OperationExecutionError(RuntimeError):
    def __init__(self, error_code: str, message: str | None = None) -> None:
        super().__init__(message or error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class FileObservation:
    size_bytes: int
    mtime_ns: int
    sha256: str


class OperationJournal:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self.events: list[dict[str, Any]] = []

    def plan_started(self, plan: OperationPlan) -> None:
        self._append({"event": "plan_started", "plan_id": plan.plan_id})

    def plan_completed(self, plan: OperationPlan) -> None:
        self._append({"event": "plan_completed", "plan_id": plan.plan_id})

    def plan_failed(self, plan: OperationPlan, error_code: str) -> None:
        self._append(
            {"event": "plan_failed", "plan_id": plan.plan_id, "error_code": error_code}
        )

    def step_started(self, plan: OperationPlan, step: OperationStep) -> None:
        event = {
            "event": "step_started",
            "plan_id": plan.plan_id,
            "step_id": step.step_id,
            "operation": step.operation,
        }
        self._append(event)
        self._update_step(plan, step, status="started", journal_event=event)

    def step_completed(
        self,
        plan: OperationPlan,
        step: OperationStep,
        observed: FileObservation | None,
    ) -> None:
        event: dict[str, Any] = {
            "event": "step_completed",
            "plan_id": plan.plan_id,
            "step_id": step.step_id,
        }
        if observed is not None:
            event.update(
                {
                    "observed_size_bytes": observed.size_bytes,
                    "observed_mtime_ns": observed.mtime_ns,
                    "observed_sha256": observed.sha256,
                }
            )
        self._append(event)
        self._update_step(plan, step, status="completed", journal_event=event)

    def step_failed(
        self,
        plan: OperationPlan,
        step: OperationStep,
        error_code: str,
    ) -> None:
        event = {
            "event": "step_failed",
            "plan_id": plan.plan_id,
            "step_id": step.step_id,
            "error_code": error_code,
        }
        self._append(event)
        self._update_step(plan, step, status="failed", journal_event=event)

    def _append(self, event: dict[str, Any]) -> None:
        self.events.append(redact_payload(event))

    def _update_step(
        self,
        plan: OperationPlan,
        step: OperationStep,
        *,
        status: str,
        journal_event: dict[str, Any],
    ) -> None:
        if self._session is None:
            return
        row = self._session.scalar(
            select(OperationStepModel)
            .join(OperationPlanModel)
            .where(
                OperationPlanModel.plan_id == plan.plan_id,
                OperationStepModel.step_id == step.step_id,
            )
        )
        if row is None:
            return
        step_json = dict(row.step_json or {})
        journal = list(step_json.get("journal") or [])
        journal.append(redact_payload(journal_event))
        step_json["journal"] = journal
        row.step_json = step_json
        row.status = status
        self._session.flush()


class OperationExecutor:
    def __init__(
        self,
        storage_roots: StorageRootService,
        *,
        journal: OperationJournal | None = None,
        after_copy: Callable[[Path], None] | None = None,
    ) -> None:
        self._storage_roots = storage_roots
        self._journal = journal or OperationJournal()
        self._after_copy = after_copy

    def execute(self, plan: OperationPlan) -> None:
        logger.info(
            "Operation plan execution started plan_id=%s mode=%s steps=%s",
            plan.plan_id,
            plan.mode,
            len(plan.steps),
        )
        self._journal.plan_started(plan)
        try:
            for step in plan.steps:
                logger.info(
                    "Operation step started plan_id=%s step_id=%s operation=%s category=%s target=%s",
                    plan.plan_id,
                    step.step_id,
                    step.operation,
                    step.category,
                    step.target_path,
                )
                self._journal.step_started(plan, step)
                observed = self._execute_step(plan, step)
                self._journal.step_completed(plan, step, observed)
                logger.info(
                    "Operation step completed plan_id=%s step_id=%s size=%s",
                    plan.plan_id,
                    step.step_id,
                    observed.size_bytes if observed is not None else None,
                )
        except OperationExecutionError as exc:
            self._journal.step_failed(plan, step, exc.error_code)
            self._journal.plan_failed(plan, exc.error_code)
            logger.error(
                "Operation plan execution failed plan_id=%s step_id=%s error_code=%s",
                plan.plan_id,
                step.step_id,
                exc.error_code,
            )
            raise
        self._journal.plan_completed(plan)
        logger.info("Operation plan execution completed plan_id=%s", plan.plan_id)

    def _execute_step(
        self,
        plan: OperationPlan,
        step: OperationStep,
    ) -> FileObservation | None:
        if step.operation == "preview":
            return None

        _resolve_for_step(self._storage_roots, step, create_parent=True)

        if step.operation in {"rename", "move"}:
            self._move(plan, step)
        elif step.operation == "copy":
            self._copy_with_temp(plan, step, remove_source=False)
        elif step.operation == "hardlink":
            self._hardlink(step)
        elif step.operation == "symlink":
            self._symlink(step)
        elif step.operation == "write_generated":
            self._write_generated(plan, step)
        else:  # pragma: no cover - guarded by schema literals.
            raise OperationExecutionError("unsupported_operation")

        if step.target_path.exists():
            return observe_file(step.target_path)
        return None

    def _move(self, plan: OperationPlan, step: OperationStep) -> None:
        source = _required_source(step)
        _verify_source_integrity(step)
        _ensure_target_absent(step.target_path)
        try:
            source.rename(step.target_path)
            _fsync_directory(source.parent)
            _fsync_directory(step.target_path.parent)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise OperationExecutionError("move_failed") from exc
            self._copy_with_temp(plan, step, remove_source=True)

    def _copy_with_temp(
        self,
        plan: OperationPlan,
        step: OperationStep,
        *,
        remove_source: bool,
    ) -> None:
        source = _required_source(step)
        _resolve_for_step(self._storage_roots, step, create_parent=True)
        source_observed = _verify_source_integrity(step)
        _ensure_target_absent(step.target_path)
        temp_path = temp_path_for_step(plan, step)
        if temp_path.exists() or temp_path.is_symlink():
            raise OperationExecutionError("temp_path_exists")

        try:
            with source.open("rb") as source_handle, temp_path.open("xb") as temp_handle:
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    temp_handle.write(chunk)
                temp_handle.flush()
                os.fsync(temp_handle.fileno())
            shutil.copystat(source, temp_path, follow_symlinks=False)
            _fsync_file(temp_path)
            if self._after_copy is not None:
                self._after_copy(temp_path)
            temp_observed = observe_file(temp_path)
            if (
                temp_observed.size_bytes != source_observed.size_bytes
                or temp_observed.sha256 != source_observed.sha256
            ):
                _unlink_if_exists(temp_path)
                raise OperationExecutionError("target_integrity_mismatch")
            _atomic_finalize_no_overwrite(temp_path, step.target_path)
            _fsync_directory(step.target_path.parent)
            target_observed = observe_file(step.target_path)
            if (
                target_observed.size_bytes != source_observed.size_bytes
                or target_observed.sha256 != source_observed.sha256
            ):
                _unlink_if_exists(step.target_path)
                raise OperationExecutionError("target_integrity_mismatch")
            if remove_source:
                _resolve_for_step(self._storage_roots, step, create_parent=False)
                latest_source = observe_file(source)
                if latest_source.sha256 != source_observed.sha256:
                    raise OperationExecutionError("source_integrity_mismatch")
                source.unlink()
                _fsync_directory(source.parent)
        except OperationExecutionError:
            _unlink_if_exists(temp_path)
            raise
        except OSError as exc:
            _unlink_if_exists(temp_path)
            raise OperationExecutionError("copy_failed") from exc

    def _hardlink(self, step: OperationStep) -> None:
        source = _required_source(step)
        _verify_source_integrity(step)
        _ensure_target_absent(step.target_path)
        try:
            os.link(source, step.target_path, follow_symlinks=False)
            _fsync_directory(step.target_path.parent)
        except FileExistsError as exc:
            raise OperationExecutionError("target_exists") from exc
        except OSError as exc:
            raise OperationExecutionError("hardlink_failed") from exc

    def _symlink(self, step: OperationStep) -> None:
        source = _required_source(step)
        _verify_source_integrity(step)
        _ensure_target_absent(step.target_path)
        try:
            os.symlink(source, step.target_path)
            _fsync_directory(step.target_path.parent)
        except FileExistsError as exc:
            raise OperationExecutionError("target_exists") from exc
        except OSError as exc:
            raise OperationExecutionError("symlink_failed") from exc

    def _write_generated(self, plan: OperationPlan, step: OperationStep) -> None:
        _ensure_target_absent(
            step.target_path,
            allow_replace=step.allow_existing_generated_replacement,
        )
        temp_path = temp_path_for_step(plan, step)
        if temp_path.exists() or temp_path.is_symlink():
            raise OperationExecutionError("temp_path_exists")
        content = str(step.metadata.get("content_text") or "").encode("utf-8")
        try:
            with temp_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            observed = observe_file(temp_path)
            if step.expected_size_bytes is not None and observed.size_bytes != step.expected_size_bytes:
                raise OperationExecutionError("target_integrity_mismatch")
            if step.sha256 is not None and observed.sha256 != step.sha256:
                raise OperationExecutionError("target_integrity_mismatch")
            if step.target_path.exists() and step.allow_existing_generated_replacement:
                step.target_path.unlink()
            _atomic_finalize_no_overwrite(temp_path, step.target_path)
            _fsync_directory(step.target_path.parent)
        except OperationExecutionError:
            _unlink_if_exists(temp_path)
            raise
        except OSError as exc:
            _unlink_if_exists(temp_path)
            raise OperationExecutionError("write_generated_failed") from exc


def temp_path_for_step(plan: OperationPlan, step: OperationStep) -> Path:
    return step.temp_parent_path / f".xona.{plan.plan_id}.{step.step_id}.tmp"


def observe_file(path: Path) -> FileObservation:
    if not path.exists() or not path.is_file():
        raise OperationExecutionError("target_missing")
    stat = path.stat()
    return FileObservation(
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=_hash_file(path),
    )


def _resolve_for_step(
    storage_roots: StorageRootService,
    step: OperationStep,
    *,
    create_parent: bool,
) -> None:
    paths = [step.target_path, step.target_path.parent, step.temp_parent_path]
    if step.source_path is not None:
        paths.insert(0, step.source_path)

    for path in paths:
        _ensure_no_symlink_ancestors(path, include_self=path == step.source_path)

    if create_parent:
        try:
            step.target_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OperationExecutionError("target_parent_unavailable") from exc

    for path in paths:
        if step.materialized_asset and path == step.source_path:
            continue
        _ensure_inside_root(storage_roots, path)
        _ensure_no_symlink_ancestors(path, include_self=path == step.source_path)

    if step.source_path is not None:
        if not step.source_path.exists() or not step.source_path.is_file():
            raise OperationExecutionError("source_missing")
    _verify_directory_no_follow(step.target_path.parent)
    _verify_directory_no_follow(step.temp_parent_path)


def _ensure_inside_root(storage_roots: StorageRootService, path: Path) -> None:
    try:
        storage_roots.validate_inside_root(path)
    except StorageRootValidationError as exc:
        raise OperationExecutionError("outside_storage_root") from exc


def _ensure_no_symlink_ancestors(path: Path, *, include_self: bool = False) -> None:
    current = path if include_self else path.parent
    candidates = [current, *current.parents]
    for candidate in candidates:
        if candidate.exists() or candidate.is_symlink():
            if candidate.is_symlink():
                raise OperationExecutionError("symlink_ancestor")


def _verify_directory_no_follow(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise OperationExecutionError("symlink_ancestor") from exc
        raise OperationExecutionError("target_parent_unavailable") from exc
    else:
        os.close(fd)


def _required_source(step: OperationStep) -> Path:
    if step.source_path is None:
        raise OperationExecutionError("source_missing")
    return step.source_path


def _verify_source_integrity(step: OperationStep) -> FileObservation:
    source = _required_source(step)
    observed = observe_file(source)
    if step.expected_size_bytes is not None and observed.size_bytes != step.expected_size_bytes:
        raise OperationExecutionError("source_integrity_mismatch")
    if step.sha256 is not None and observed.sha256 != step.sha256:
        raise OperationExecutionError("source_integrity_mismatch")
    return observed


def _ensure_target_absent(path: Path, *, allow_replace: bool = False) -> None:
    if path.exists() or path.is_symlink():
        if allow_replace:
            return
        raise OperationExecutionError("target_exists")


def _atomic_finalize_no_overwrite(temp_path: Path, target_path: Path) -> None:
    try:
        os.link(temp_path, target_path)
    except FileExistsError as exc:
        raise OperationExecutionError("target_exists") from exc
    except OSError as exc:
        raise OperationExecutionError("finalize_failed") from exc
    finally:
        _unlink_if_exists(temp_path)


def _unlink_if_exists(path: Path) -> None:
    try:
        if path.exists() or path.is_symlink():
            path.unlink()
    except FileNotFoundError:
        return


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_stale_temp_files(plan: OperationPlan) -> None:
    for step in plan.steps:
        temp = temp_path_for_step(plan, step)
        if temp.exists() or temp.is_symlink():
            try:
                temp.unlink()
                logger.info(
                    "Cleaned up stale temp file plan_id=%s step_id=%s path=%s",
                    plan.plan_id, step.step_id, temp,
                )
            except OSError:
                pass
