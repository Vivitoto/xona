from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.services.stability import StabilityDetector, StabilitySnapshot


def test_file_becomes_stable_after_unchanged_checks_and_minimum_age(tmp_path: Path) -> None:
    path = tmp_path / "movie.mkv"
    path.write_bytes(b"movie")
    now = datetime.now(timezone.utc)
    old_mtime_ns = int((now - timedelta(seconds=90)).timestamp() * 1_000_000_000)
    fresh_mtime_ns = int((now - timedelta(seconds=5)).timestamp() * 1_000_000_000)
    detector = StabilityDetector(minimum_age_seconds=30, required_stable_checks=2)

    fresh = detector.evaluate(
        path,
        previous=None,
        size_bytes=5,
        mtime_ns=fresh_mtime_ns,
        now=now,
    )
    assert fresh.stable is False
    assert fresh.reason == "too_new"

    first = detector.evaluate(
        path,
        previous=StabilitySnapshot(size_bytes=5, mtime_ns=old_mtime_ns, stable_count=0),
        size_bytes=5,
        mtime_ns=old_mtime_ns,
        now=now,
    )
    second = detector.evaluate(
        path,
        previous=first.snapshot,
        size_bytes=5,
        mtime_ns=old_mtime_ns,
        now=now,
    )
    assert first.stable is False
    assert first.snapshot.stable_count == 1
    assert second.stable is True
    assert second.snapshot.stable_count == 2


def test_temporary_markers_prevent_stability(tmp_path: Path) -> None:
    path = tmp_path / "movie.mkv"
    path.write_bytes(b"movie")
    (tmp_path / "movie.mkv.part").write_bytes(b"partial")
    now = datetime.now(timezone.utc)
    mtime_ns = int((now - timedelta(seconds=90)).timestamp() * 1_000_000_000)

    result = StabilityDetector(
        minimum_age_seconds=30,
        required_stable_checks=1,
    ).evaluate(
        path,
        previous=StabilitySnapshot(size_bytes=5, mtime_ns=mtime_ns, stable_count=0),
        size_bytes=5,
        mtime_ns=mtime_ns,
        now=now,
    )

    assert result.stable is False
    assert result.reason == "temporary_marker"
