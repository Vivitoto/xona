from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    LocalMetadataBatch,
    LocalMetadataBatchItem,
)
from backend.app.schemas.local_metadata import (
    LocalAnalyzeRequest,
    LocalBatchCoverSettings,
    LocalCacheCleanupResponse,
    LocalCachedAsset,
    LocalCoverPreviewRequest,
    LocalCoverPreviewResponse,
    LocalExecutePlanResponse,
    LocalFrameRequest,
    LocalMetadataBatchCreateRequest,
    LocalMetadataBatchItemRead,
    LocalMetadataBatchListResponse,
    LocalMetadataBatchLogEntry,
    LocalMetadataBatchOptions,
    LocalMetadataBatchRead,
    LocalMetadataBatchSummary,
    LocalMetadataDraft,
    LocalPlanPreviewRequest,
    LocalPlanPreviewResponse,
)
from backend.app.services.cover_templates import SIMILAR_FRAMES_FALLBACK_WARNING
from backend.app.services.local_metadata import LocalMetadataError, LocalMetadataService

logger = logging.getLogger(__name__)

MAX_BATCH_ITEM_LOGS = 12
MIN_COVER_FRAME_COUNT = 9
DESTRUCTIVE_BATCH_PLAN_MODES = {"move", "in_place"}
ACTIVE_BATCH_STATUSES = {"queued", "running"}


class LocalMetadataBatchError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int = 400,
        reasons: list[str] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.reasons = reasons or [code]


class _BatchCancelled(Exception):
    pass


class LocalMetadataBatchService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_batch(self, payload: LocalMetadataBatchCreateRequest) -> LocalMetadataBatch:
        now = _utcnow()
        batch = LocalMetadataBatch(
            batch_id=f"lmb_{uuid.uuid4().hex}",
            status="queued",
            options_json=payload.options.model_dump(mode="json"),
            total_count=len(payload.items),
            pending_count=len(payload.items),
            running_count=0,
            succeeded_count=0,
            failed_count=0,
            executable_count=0,
            executed_count=0,
            execute_failed_count=0,
            updated_at=now,
        )
        self._session.add(batch)
        self._session.flush()
        for sequence, item in enumerate(payload.items):
            draft = item.metadata.model_copy(update={"video_path": item.video_path})
            filename = item.filename or Path(item.video_path).name
            batch.items.append(
                LocalMetadataBatchItem(
                    batch_id=batch.id,
                    sequence=sequence,
                    video_path=str(item.video_path),
                    filename=filename,
                    draft_json=draft.model_dump(mode="json"),
                    cover_settings_json=item.cover_settings.model_dump(mode="json"),
                    status="pending",
                    error=None,
                    logs_json=[],
                    frames_json=[],
                    selected_frame_ids_json=[],
                    cover_preview_json=None,
                    plan_id=None,
                    plan_preview_json=None,
                    result_json=None,
                    updated_at=now,
                )
            )
        self._session.flush()
        return batch

    def list_batches(self, *, limit: int = 20) -> LocalMetadataBatchListResponse:
        statement = (
            select(LocalMetadataBatch)
            .order_by(LocalMetadataBatch.updated_at.desc(), LocalMetadataBatch.id.desc())
            .limit(max(1, min(100, limit)))
        )
        batches = list(self._session.scalars(statement))
        return LocalMetadataBatchListResponse(
            batches=[batch_summary(batch) for batch in batches],
        )

    def get_batch(self, batch_id: str) -> LocalMetadataBatch:
        batch = self._session.scalar(_batch_by_public_id(batch_id))
        if batch is None:
            raise LocalMetadataBatchError("batch_not_found", status_code=404)
        return batch

    def cancel_batch(self, batch_id: str) -> LocalMetadataBatch:
        batch = self.get_batch(batch_id)
        now = _utcnow()
        batch.status = "cancelled"
        batch.updated_at = now
        for item in batch.items:
            if item.status in {"pending", "running", "executing"}:
                item.status = "cancelled"
                item.updated_at = now
                _append_item_log(item, "warning", "批量任务已取消", now=now)
        recalculate_batch_counts(batch)
        return batch

    def retry_failed(self, batch_id: str) -> tuple[LocalMetadataBatch, bool, bool]:
        batch = self.get_batch(batch_id)
        now = _utcnow()
        preview_retry = False
        execute_retry = False
        for item in batch.items:
            if item.status == "failed":
                item.status = "pending"
                item.error = None
                item.plan_id = None
                item.plan_preview_json = None
                item.result_json = None
                item.updated_at = now
                _append_item_log(item, "active", "失败条目已重新排队", now=now)
                preview_retry = True
            elif item.status == "execute_failed":
                item.status = "succeeded"
                item.error = None
                item.result_json = None
                item.updated_at = now
                _append_item_log(item, "active", "执行失败条目可重新执行", now=now)
                execute_retry = True
        if not preview_retry and not execute_retry:
            raise LocalMetadataBatchError(
                "batch_has_no_failed_items",
                status_code=409,
            )
        batch.status = "queued" if preview_retry else "running"
        batch.updated_at = now
        recalculate_batch_counts(batch)
        return batch, preview_retry, execute_retry and not preview_retry


class LocalMetadataBatchManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._tasks: dict[tuple[str, str], asyncio.Task[None]] = {}

    def start_preview(self, batch_id: str) -> None:
        key = (batch_id, "preview")
        if self._has_active_task(key):
            return
        self._start_task(key, self._run_preview_batch(batch_id))

    def start_execute(self, batch_id: str) -> None:
        key = (batch_id, "execute")
        if self._has_active_task(key):
            return
        self._start_task(key, self._run_execute_batch(batch_id))

    def recover_interrupted_batches(self) -> None:
        """Recover persisted batches after a server restart.

        Preview work is safe to resume because it only regenerates cached metadata
        previews. Execution work may already have moved/copied files before the
        process died, so interrupted executing items are marked for manual retry
        instead of being run again automatically.
        """
        preview_batch_ids = self._recover_interrupted_batches()
        for batch_id in preview_batch_ids:
            self.start_preview(batch_id)

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _recover_interrupted_batches(self) -> list[str]:
        preview_batch_ids: list[str] = []
        with self._session_factory() as session:
            batches = list(
                session.scalars(
                    select(LocalMetadataBatch).where(
                        LocalMetadataBatch.status.in_(ACTIVE_BATCH_STATUSES)
                    )
                )
            )
            now = _utcnow()
            for batch in batches:
                changed = False
                for item in batch.items:
                    if item.status == "running":
                        item.status = "pending"
                        item.error = None
                        item.updated_at = now
                        _append_item_log(
                            item,
                            "warning",
                            "服务重启后已恢复为等待处理",
                            now=now,
                        )
                        changed = True
                    elif item.status == "executing":
                        item.status = "execute_failed"
                        item.error = "服务重启时整理执行中断；请检查目标文件后手动重试。"
                        item.updated_at = now
                        _append_item_log(item, "warning", item.error, now=now)
                        changed = True
                recalculate_batch_counts(batch)
                if batch.pending_count:
                    batch.status = "queued"
                    preview_batch_ids.append(batch.batch_id)
                    changed = True
                elif batch.failed_count or batch.execute_failed_count:
                    batch.status = "completed_with_errors"
                    changed = True
                elif batch.total_count:
                    batch.status = "completed"
                    changed = True
                if changed:
                    batch.updated_at = now
            session.commit()
        return preview_batch_ids

    def _has_active_task(self, key: tuple[str, str]) -> bool:
        existing = self._tasks.get(key)
        return existing is not None and not existing.done()

    def _start_task(self, key: tuple[str, str], coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks[key] = task
        def forget_finished_task(_finished: asyncio.Task[None], task_key: tuple[str, str] = key) -> None:
            self._tasks.pop(task_key, None)

        task.add_done_callback(forget_finished_task)

    async def _run_preview_batch(self, batch_id: str) -> None:
        try:
            item_ids, concurrency = await asyncio.to_thread(
                self._prepare_preview_batch,
                batch_id,
            )
            semaphore = asyncio.Semaphore(concurrency)

            async def run_item(item_id: int) -> None:
                async with semaphore:
                    await asyncio.to_thread(self._process_preview_item, item_id)

            await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
            await asyncio.to_thread(self._finish_batch, batch_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Local metadata batch preview runner failed batch_id=%s", batch_id)
            await asyncio.to_thread(self._mark_batch_failed, batch_id)

    async def _run_execute_batch(self, batch_id: str) -> None:
        try:
            item_ids, concurrency = await asyncio.to_thread(
                self._prepare_execute_batch,
                batch_id,
            )
            semaphore = asyncio.Semaphore(concurrency)

            async def run_item(item_id: int) -> None:
                async with semaphore:
                    await asyncio.to_thread(self._process_execute_item, item_id)

            await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
            await asyncio.to_thread(self._finish_batch, batch_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Local metadata batch execute runner failed batch_id=%s", batch_id)
            await asyncio.to_thread(self._mark_batch_failed, batch_id)

    def _prepare_preview_batch(self, batch_id: str) -> tuple[list[int], int]:
        with self._session_factory() as session:
            batch = LocalMetadataBatchService(session).get_batch(batch_id)
            if batch.status == "cancelled":
                session.commit()
                return [], 1
            options = _batch_options(batch)
            now = _utcnow()
            batch.status = "running"
            batch.updated_at = now
            item_ids = [
                item.id
                for item in batch.items
                if item.status == "pending"
            ]
            recalculate_batch_counts(batch)
            session.commit()
            return item_ids, _clamped_concurrency(options.concurrency)

    def _prepare_execute_batch(self, batch_id: str) -> tuple[list[int], int]:
        with self._session_factory() as session:
            batch = LocalMetadataBatchService(session).get_batch(batch_id)
            if batch.status == "cancelled":
                session.commit()
                return [], 1
            options = _batch_options(batch)
            now = _utcnow()
            batch.status = "running"
            batch.updated_at = now
            candidates = [
                item
                for item in batch.items
                if item.status in {"succeeded", "execute_failed"}
                and item.plan_id
                and item.result_json is None
            ]
            item_ids: list[int] = []
            skipped_ids = _duplicate_destructive_item_ids(candidates)
            for item in candidates:
                if item.id in skipped_ids:
                    item.status = "execute_failed"
                    item.error = (
                        "同一个源文件已有移动整理计划会先执行；此重复计划已跳过。"
                    )
                    item.updated_at = now
                    _append_item_log(item, "warning", item.error, now=now)
                    continue
                if _plan_mode(item) == "preview":
                    continue
                item_ids.append(item.id)
            concurrency = 1 if any(_is_destructive_item(item) for item in candidates) else options.concurrency
            recalculate_batch_counts(batch)
            session.commit()
            return item_ids, _clamped_concurrency(concurrency)

    def _process_preview_item(self, item_id: int) -> None:
        with self._session_factory() as session:
            item = session.get(LocalMetadataBatchItem, item_id)
            if item is None or item.status != "pending":
                session.commit()
                return
            batch = item.batch
            options = _batch_options(batch)
            now = _utcnow()
            item.status = "running"
            item.error = None
            item.updated_at = now
            _append_item_log(item, "active", "开始处理", now=now)
            recalculate_batch_counts(batch)
            session.commit()

            try:
                service = LocalMetadataService(self._settings, session)
                self._ensure_not_cancelled(session, batch.id, item.id)

                _append_and_commit(session, batch, item, "active", "正在分析视频")
                analyze_response = service.analyze(
                    LocalAnalyzeRequest(video_path=Path(item.video_path))
                )
                draft = LocalMetadataDraft.model_validate(item.draft_json).model_copy(
                    update={
                        "video_path": analyze_response.video_path,
                        "runtime_minutes": _runtime_minutes(
                            analyze_response.technical.duration_seconds
                        ),
                        "technical": analyze_response.technical,
                    }
                )
                item.draft_json = draft.model_dump(mode="json")
                _append_and_commit(session, batch, item, "success", "分析完成")
                self._ensure_not_cancelled(session, batch.id, item.id)

                _append_and_commit(
                    session,
                    batch,
                    item,
                    "active",
                    f"正在生成 {options.frame_count} 张截图",
                )
                frame_response = service.generate_frames(
                    LocalFrameRequest(
                        video_path=analyze_response.video_path,
                        frame_count=options.frame_count,
                        duration_seconds=analyze_response.technical.duration_seconds,
                    )
                )
                selected_frame_ids = _selected_initial_frame_ids(frame_response.frames)
                if len(selected_frame_ids) < MIN_COVER_FRAME_COUNT:
                    raise LocalMetadataError(
                        "frame_required",
                        reasons=[
                            f"截图不足，至少需要 {MIN_COVER_FRAME_COUNT} 张用于封面。"
                        ],
                    )
                item.frames_json = [
                    frame.model_dump(mode="json") for frame in frame_response.frames
                ]
                item.selected_frame_ids_json = selected_frame_ids
                _append_and_commit(
                    session,
                    batch,
                    item,
                    "success",
                    f"截图完成，已选择 {len(selected_frame_ids)} 张封面素材",
                )
                self._ensure_not_cancelled(session, batch.id, item.id)

                _append_and_commit(session, batch, item, "active", "正在生成封面预览")
                cover_settings = LocalBatchCoverSettings.model_validate(
                    item.cover_settings_json
                )
                cover_response = service.cover_preview(
                    LocalCoverPreviewRequest(
                        video_path=analyze_response.video_path,
                        title=draft.title,
                        selected_frame_ids=selected_frame_ids,
                        **cover_settings.model_dump(mode="python"),
                    )
                )
                item.cover_preview_json = cover_response.model_dump(mode="json")
                now = _utcnow()
                for warning in cover_response.warnings:
                    if warning == SIMILAR_FRAMES_FALLBACK_WARNING:
                        _append_item_log(
                            item,
                            "warning",
                            f"{warning}: 内容相近截图不足 9 张，已用相似帧补足封面素材。",
                            now=now,
                        )
                    else:
                        _append_item_log(item, "warning", warning, now=now)
                _append_and_commit(session, batch, item, "success", "封面预览已生成")
                self._ensure_not_cancelled(session, batch.id, item.id)

                _append_and_commit(session, batch, item, "active", "正在生成 NFO 与整理计划")
                plan_response = service.preview_plan(
                    LocalPlanPreviewRequest(
                        metadata=draft,
                        destination_root=options.destination_root,
                        mode=options.mode,
                        folder_templates=options.folder_templates,
                        filename_template=options.filename_template,
                        poster_ref=cover_response.poster.id,
                        fanart_ref=cover_response.fanart.id,
                        thumb_ref=cover_response.thumb.id,
                        selected_frame_ids=selected_frame_ids,
                        extra_backdrop_count=options.extra_backdrop_count,
                    )
                )
                item.plan_id = plan_response.plan_id
                item.plan_preview_json = plan_response.model_dump(mode="json")
                item.status = "succeeded"
                item.error = None
                item.updated_at = _utcnow()
                _append_item_log(
                    item,
                    "success",
                    f"NFO 与整理计划已生成，计划 {plan_response.plan_id}",
                )
                recalculate_batch_counts(batch)
                session.commit()
            except _BatchCancelled:
                session.rollback()
                self._mark_item_cancelled(item_id)
            except Exception as exc:
                session.rollback()
                self._mark_item_failed(item_id, _error_message(exc))

    def _process_execute_item(self, item_id: int) -> None:
        with self._session_factory() as session:
            item = session.get(LocalMetadataBatchItem, item_id)
            if item is None or item.status not in {"succeeded", "execute_failed"}:
                session.commit()
                return
            if not item.plan_id or item.plan_preview_json is None:
                session.commit()
                return
            batch = item.batch
            options = _batch_options(batch)
            plan_preview = LocalPlanPreviewResponse.model_validate(item.plan_preview_json)
            plan_payload = plan_preview.plan
            plan_mode = str(plan_payload.get("mode", ""))
            plan_version = int(plan_payload.get("version", 1))
            if plan_mode == "preview":
                session.commit()
                return

            now = _utcnow()
            item.status = "executing"
            item.error = None
            item.updated_at = now
            _append_item_log(item, "active", f"正在执行整理计划 {item.plan_id}", now=now)
            recalculate_batch_counts(batch)
            session.commit()

            try:
                service = LocalMetadataService(self._settings, session)
                self._ensure_not_cancelled(session, batch.id, item.id)
                response = service.execute_plan(
                    item.plan_id,
                    approved=True,
                    plan_version=plan_version,
                )
                item.result_json = response.model_dump(mode="json")
                item.status = "executed"
                item.error = None
                item.updated_at = _utcnow()
                _append_item_log(
                    item,
                    "success",
                    "整理执行完成"
                    if response.state == "completed"
                    else f"整理执行状态：{response.state}",
                )
                recalculate_batch_counts(batch)
                session.commit()

                if response.state == "completed" and options.cleanup_cache_after_execute:
                    self._cleanup_executed_cache(item_id, plan_version)
            except _BatchCancelled:
                session.rollback()
                self._mark_item_cancelled(item_id)
            except Exception as exc:
                session.rollback()
                self._mark_item_execute_failed(item_id, _error_message(exc))

    def _cleanup_executed_cache(self, item_id: int, plan_version: int) -> None:
        with self._session_factory() as session:
            item = session.get(LocalMetadataBatchItem, item_id)
            if item is None or item.plan_id is None:
                session.commit()
                return
            batch = item.batch
            service = LocalMetadataService(self._settings, session)
            try:
                _append_and_commit(session, batch, item, "active", "正在清理本地元数据缓存")
                response = service.cleanup_plan_cache(
                    item.plan_id,
                    plan_version=plan_version,
                )
                _append_item_log(
                    item,
                    "success",
                    _cleanup_message(response),
                )
                for warning in response.warnings:
                    _append_item_log(item, "warning", f"缓存清理提示：{warning}")
                item.updated_at = _utcnow()
                batch.updated_at = item.updated_at
                session.commit()
            except Exception as exc:
                session.rollback()
                with self._session_factory() as retry_session:
                    retry_item = retry_session.get(LocalMetadataBatchItem, item_id)
                    if retry_item is not None:
                        retry_batch = retry_item.batch
                        _append_item_log(
                            retry_item,
                            "warning",
                            f"本地元数据缓存清理失败：{_error_message(exc)}",
                        )
                        retry_item.updated_at = _utcnow()
                        retry_batch.updated_at = retry_item.updated_at
                        retry_session.commit()

    def _finish_batch(self, batch_id: str) -> None:
        with self._session_factory() as session:
            batch = LocalMetadataBatchService(session).get_batch(batch_id)
            if batch.status == "cancelled":
                recalculate_batch_counts(batch)
                session.commit()
                return
            recalculate_batch_counts(batch)
            if batch.running_count or batch.pending_count:
                batch.status = "running"
            elif batch.failed_count or batch.execute_failed_count:
                batch.status = "completed_with_errors"
            else:
                batch.status = "completed"
            batch.updated_at = _utcnow()
            session.commit()

    def _mark_batch_failed(self, batch_id: str) -> None:
        with self._session_factory() as session:
            batch = LocalMetadataBatchService(session).get_batch(batch_id)
            if batch.status != "cancelled":
                batch.status = "failed"
                batch.updated_at = _utcnow()
            recalculate_batch_counts(batch)
            session.commit()

    def _mark_item_failed(self, item_id: int, message: str) -> None:
        self._mark_item_terminal(item_id, "failed", message)

    def _mark_item_execute_failed(self, item_id: int, message: str) -> None:
        self._mark_item_terminal(item_id, "execute_failed", message)

    def _mark_item_cancelled(self, item_id: int) -> None:
        self._mark_item_terminal(item_id, "cancelled", "批量任务已取消", tone="warning")

    def _mark_item_terminal(
        self,
        item_id: int,
        status: str,
        message: str,
        *,
        tone: str = "danger",
    ) -> None:
        with self._session_factory() as session:
            item = session.get(LocalMetadataBatchItem, item_id)
            if item is None:
                session.commit()
                return
            batch = item.batch
            now = _utcnow()
            item.status = status
            item.error = message
            item.updated_at = now
            _append_item_log(item, tone, message, now=now)
            recalculate_batch_counts(batch)
            session.commit()

    def _ensure_not_cancelled(
        self,
        session: Session,
        batch_database_id: int,
        item_id: int,
    ) -> None:
        status = session.scalar(
            select(LocalMetadataBatch.status).where(
                LocalMetadataBatch.id == batch_database_id
            )
        )
        item_status = session.scalar(
            select(LocalMetadataBatchItem.status).where(
                LocalMetadataBatchItem.id == item_id
            )
        )
        if status == "cancelled" or item_status == "cancelled":
            raise _BatchCancelled


def batch_read(batch: LocalMetadataBatch) -> LocalMetadataBatchRead:
    summary = batch_summary(batch)
    return LocalMetadataBatchRead(
        **summary.model_dump(),
        items=[batch_item_read(item) for item in sorted(batch.items, key=lambda row: row.sequence)],
    )


def batch_summary(batch: LocalMetadataBatch) -> LocalMetadataBatchSummary:
    return LocalMetadataBatchSummary(
        batch_id=batch.batch_id,
        status=batch.status,  # type: ignore[arg-type]
        options=_batch_options(batch),
        total_count=batch.total_count,
        pending_count=batch.pending_count,
        running_count=batch.running_count,
        succeeded_count=batch.succeeded_count,
        failed_count=batch.failed_count,
        executable_count=batch.executable_count,
        executed_count=batch.executed_count,
        execute_failed_count=batch.execute_failed_count,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


def batch_item_read(item: LocalMetadataBatchItem) -> LocalMetadataBatchItemRead:
    return LocalMetadataBatchItemRead(
        item_id=item.id,
        video_path=Path(item.video_path),
        filename=item.filename,
        draft=LocalMetadataDraft.model_validate(item.draft_json),
        cover_settings=LocalBatchCoverSettings.model_validate(item.cover_settings_json),
        status=item.status,  # type: ignore[arg-type]
        error=item.error,
        logs=[
            LocalMetadataBatchLogEntry.model_validate(entry)
            for entry in (item.logs_json or [])
        ],
        frames=[
            LocalCachedAsset.model_validate(entry)
            for entry in (item.frames_json or [])
        ],
        selected_frame_ids=list(item.selected_frame_ids_json or []),
        cover_preview=(
            LocalCoverPreviewResponse.model_validate(item.cover_preview_json)
            if item.cover_preview_json is not None
            else None
        ),
        plan_id=item.plan_id,
        plan_preview=(
            LocalPlanPreviewResponse.model_validate(item.plan_preview_json)
            if item.plan_preview_json is not None
            else None
        ),
        execute_result=(
            LocalExecutePlanResponse.model_validate(item.result_json)
            if item.result_json is not None
            else None
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def recalculate_batch_counts(batch: LocalMetadataBatch) -> None:
    items = list(batch.items)
    batch.total_count = len(items)
    batch.pending_count = sum(1 for item in items if item.status == "pending")
    batch.running_count = sum(1 for item in items if item.status in {"running", "executing"})
    batch.succeeded_count = sum(
        1 for item in items if item.status in {"succeeded", "executing", "executed"}
    )
    batch.failed_count = sum(1 for item in items if item.status == "failed")
    batch.executable_count = sum(1 for item in items if _is_executable_item(item))
    batch.executed_count = sum(1 for item in items if item.status == "executed")
    batch.execute_failed_count = sum(1 for item in items if item.status == "execute_failed")
    batch.updated_at = _utcnow()


def _batch_by_public_id(batch_id: str) -> Select[tuple[LocalMetadataBatch]]:
    return select(LocalMetadataBatch).where(LocalMetadataBatch.batch_id == batch_id)


def _batch_options(batch: LocalMetadataBatch) -> LocalMetadataBatchOptions:
    return LocalMetadataBatchOptions.model_validate(batch.options_json)


def _append_and_commit(
    session: Session,
    batch: LocalMetadataBatch,
    item: LocalMetadataBatchItem,
    tone: str,
    message: str,
) -> None:
    now = _utcnow()
    _append_item_log(item, tone, message, now=now)
    item.updated_at = now
    batch.updated_at = now
    recalculate_batch_counts(batch)
    session.commit()


def _append_item_log(
    item: LocalMetadataBatchItem,
    tone: str,
    message: str,
    *,
    now: datetime | None = None,
) -> None:
    timestamp = now or _utcnow()
    logs = list(item.logs_json or [])
    logs.append(
        {
            "tone": tone,
            "message": message,
            "created_at": timestamp.isoformat(),
        }
    )
    item.logs_json = logs[-MAX_BATCH_ITEM_LOGS:]


def _selected_initial_frame_ids(frames: list[Any]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for frame in frames:
        if frame.id in seen:
            continue
        seen.add(frame.id)
        selected.append(frame.id)
        if len(selected) >= MIN_COVER_FRAME_COUNT:
            break
    return selected


def _runtime_minutes(duration_seconds: float | None) -> int | None:
    if duration_seconds is None or duration_seconds <= 0:
        return None
    return max(1, round(duration_seconds / 60))


def _error_message(exc: Exception) -> str:
    if isinstance(exc, LocalMetadataBatchError):
        return "；".join(exc.reasons)
    if isinstance(exc, LocalMetadataError):
        return "；".join(exc.reasons)
    return str(exc) or exc.__class__.__name__


def _cleanup_message(response: LocalCacheCleanupResponse) -> str:
    if response.deleted_directories:
        return (
            "本地元数据缓存已清理："
            f"{response.deleted_directories} 个目录，{response.deleted_files} 个文件"
        )
    return "本地元数据缓存无需清理"


def _clamped_concurrency(value: int) -> int:
    return max(1, min(4, int(value)))


def _is_executable_item(item: LocalMetadataBatchItem) -> bool:
    return (
        item.plan_id is not None
        and item.result_json is None
        and item.status in {"succeeded", "execute_failed"}
        and _plan_mode(item) != "preview"
    )


def _is_destructive_item(item: LocalMetadataBatchItem) -> bool:
    return _plan_mode(item) in DESTRUCTIVE_BATCH_PLAN_MODES


def _plan_mode(item: LocalMetadataBatchItem) -> str | None:
    plan_preview = item.plan_preview_json
    if not isinstance(plan_preview, dict):
        return None
    plan = plan_preview.get("plan")
    if not isinstance(plan, dict):
        return None
    mode = plan.get("mode")
    return mode if isinstance(mode, str) else None


def _duplicate_destructive_item_ids(items: list[LocalMetadataBatchItem]) -> set[int]:
    seen_sources: set[str] = set()
    duplicate_ids: set[int] = set()
    for item in items:
        if not _is_destructive_item(item):
            continue
        source = _plan_media_source_path(item) or item.video_path
        if source in seen_sources:
            duplicate_ids.add(item.id)
            continue
        seen_sources.add(source)
    return duplicate_ids


def _plan_media_source_path(item: LocalMetadataBatchItem) -> str | None:
    plan_preview = item.plan_preview_json
    if not isinstance(plan_preview, dict):
        return None
    plan = plan_preview.get("plan")
    if not isinstance(plan, dict):
        return None
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("category") == "media" and isinstance(step.get("source_path"), str):
            return str(step["source_path"])
    return None


def _utcnow() -> datetime:
    return datetime.utcnow()
