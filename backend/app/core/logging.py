from __future__ import annotations

import asyncio
import logging
import sys
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.core.redaction import redact_payload

LOG_BUFFER_SIZE = 1000
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(component)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LogEntry:
    id: int
    timestamp: str
    level: str
    logger: str
    component: str
    message: str
    source: str = "application"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original_args: Any = record.args
        original_msg = record.msg
        original_component = getattr(record, "component", None)
        had_component = hasattr(record, "component")
        record.msg = redact_payload(record.msg)
        record.args = redact_payload(record.args)
        record.component = component_name(record.name)
        try:
            return super().format(record)
        finally:
            record.msg = original_msg
            record.args = original_args
            if had_component:
                record.component = original_component
            else:
                delattr(record, "component")


class InMemoryLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            entry = _append_log_entry(record, message)
            _publish(entry)
        except Exception:
            self.handleError(record)


_log_entries: deque[LogEntry] = deque(maxlen=LOG_BUFFER_SIZE)
_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[LogEntry]]] = set()
_next_log_id = 0
_configured = False


def configure_logging(
    *,
    config_dir: Path | None = None,
    level: str = "INFO",
    file_enabled: bool = True,
) -> None:
    """Configure Xona logging once.

    Logs are written to stdout so Docker captures them, mirrored to an in-memory
    ring buffer for the Web UI, and optionally persisted under /config/logs.
    """

    global _configured
    if _configured:
        return

    parsed_level = getattr(logging, level.upper(), logging.INFO)
    formatter = RedactingFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    memory_formatter = RedactingFormatter("%(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(parsed_level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(parsed_level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    memory_handler = InMemoryLogHandler()
    memory_handler.setLevel(parsed_level)
    memory_handler.setFormatter(memory_formatter)
    root_logger.addHandler(memory_handler)

    if file_enabled and config_dir is not None:
        log_dir = config_dir / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_dir / "xona.log", encoding="utf-8")
            file_handler.setLevel(parsed_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except OSError:
            logging.getLogger(__name__).warning("Unable to initialize persistent log file")

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(parsed_level)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True

    _configured = True
    logging.getLogger(__name__).info("Logging initialized level=%s", logging.getLevelName(parsed_level))


def component_name(logger_name: str) -> str:
    if logger_name == "backend.app.main":
        return "app"
    if logger_name.startswith("backend.app.api."):
        return f"api.{logger_name.rsplit('.', 1)[-1]}"
    if logger_name.startswith("backend.app.services."):
        return f"service.{logger_name.rsplit('.', 1)[-1]}"
    if logger_name.startswith("backend.app.integrations."):
        return f"integration.{logger_name.rsplit('.', 1)[-1]}"
    if logger_name.startswith("backend.app.core."):
        return f"core.{logger_name.rsplit('.', 1)[-1]}"
    if logger_name.startswith("backend.app.db."):
        return "db"
    if logger_name.startswith("uvicorn"):
        return "server"
    return logger_name


def recent_logs(*, limit: int = 200, level: str | None = None) -> list[LogEntry]:
    normalized_level = level.upper() if level else None
    entries = list(_log_entries)
    if normalized_level:
        entries = [entry for entry in entries if entry.level == normalized_level]
    return entries[-max(1, min(limit, LOG_BUFFER_SIZE)):]


async def subscribe_logs(*, since_id: int | None = None) -> AsyncIterator[LogEntry]:
    queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=200)
    loop = asyncio.get_running_loop()
    subscriber = (loop, queue)
    _subscribers.add(subscriber)
    try:
        for entry in list(_log_entries):
            if since_id is None or entry.id > since_id:
                yield entry
        while True:
            yield await queue.get()
    finally:
        _subscribers.discard(subscriber)


def _append_log_entry(record: logging.LogRecord, message: str) -> LogEntry:
    global _next_log_id
    _next_log_id += 1
    entry = LogEntry(
        id=_next_log_id,
        timestamp=datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        level=record.levelname,
        logger=record.name,
        component=component_name(record.name),
        message=str(redact_payload(message)),
    )
    _log_entries.append(entry)
    return entry


def _publish(entry: LogEntry) -> None:
    stale: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[LogEntry]]] = set()
    for loop, queue in list(_subscribers):
        if loop.is_closed():
            stale.add((loop, queue))
            continue

        def put_nowait(target: asyncio.Queue[LogEntry] = queue) -> None:
            if target.full():
                try:
                    target.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            target.put_nowait(entry)

        loop.call_soon_threadsafe(put_nowait)
    _subscribers.difference_update(stale)
