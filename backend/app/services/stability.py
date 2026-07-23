from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


TEMPORARY_SUFFIXES = (".part", ".crdownload", ".tmp")


@dataclass(frozen=True)
class StabilitySnapshot:
    size_bytes: int
    mtime_ns: int
    stable_count: int


@dataclass(frozen=True)
class StabilityResult:
    stable: bool
    reason: str | None
    snapshot: StabilitySnapshot


class StabilityDetector:
    def __init__(self, *, minimum_age_seconds: int, required_stable_checks: int) -> None:
        self._minimum_age_seconds = minimum_age_seconds
        self._required_stable_checks = required_stable_checks

    def evaluate(
        self,
        path: Path | str,
        *,
        previous: StabilitySnapshot | None,
        size_bytes: int,
        mtime_ns: int,
        now: datetime | None = None,
    ) -> StabilityResult:
        media_path = Path(path)
        now = now or datetime.now(timezone.utc)
        unchanged = (
            previous is not None
            and previous.size_bytes == size_bytes
            and previous.mtime_ns == mtime_ns
        )
        stable_count = previous.stable_count + 1 if unchanged and previous else 0
        snapshot = StabilitySnapshot(
            size_bytes=size_bytes,
            mtime_ns=mtime_ns,
            stable_count=stable_count,
        )
        if _has_temporary_marker(media_path):
            return StabilityResult(stable=False, reason="temporary_marker", snapshot=snapshot)
        mtime = datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=timezone.utc)
        if (now - mtime).total_seconds() < self._minimum_age_seconds:
            return StabilityResult(stable=False, reason="too_new", snapshot=snapshot)
        if stable_count < self._required_stable_checks:
            return StabilityResult(stable=False, reason="unstable", snapshot=snapshot)
        return StabilityResult(stable=True, reason=None, snapshot=snapshot)


def _has_temporary_marker(path: Path) -> bool:
    if path.suffix.lower() in TEMPORARY_SUFFIXES:
        return True
    for suffix in TEMPORARY_SUFFIXES:
        if (path.parent / f"{path.name}{suffix}").exists():
            return True
    return False
