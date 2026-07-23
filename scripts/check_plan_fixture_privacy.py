#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_TEST_PATH = REPO_ROOT / "tests" / "backend" / "fixtures" / "test_fixture_privacy.py"
MAX_FIXTURE_BYTES = 20_000
SKIPPED_SUFFIXES = frozenset({".py", ".pyc", ".pyo"})


def _load_privacy_rules() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_xona_fixture_privacy_rules",
        PRIVACY_TEST_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load fixture privacy rules from {PRIVACY_TEST_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_privacy_rules = _load_privacy_rules()

FIXTURE_ROOT = Path(_privacy_rules.FIXTURE_ROOT)
FORBIDDEN_LITERAL = tuple(_privacy_rules.FORBIDDEN_LITERAL)
FORBIDDEN_REGEX = tuple(_privacy_rules.FORBIDDEN_REGEX)


@dataclass(frozen=True)
class PrivacyViolation:
    path: Path
    message: str


def audit_paths(
    paths: Iterable[Path],
    *,
    max_bytes: int = MAX_FIXTURE_BYTES,
) -> tuple[PrivacyViolation, ...]:
    violations: list[PrivacyViolation] = []
    for path in paths:
        if not path.exists():
            violations.append(
                PrivacyViolation(path=_display_path(path), message="path does not exist")
            )
            continue
        for fixture_path in _iter_fixture_files(path):
            size = fixture_path.stat().st_size
            if size >= max_bytes:
                violations.append(
                    PrivacyViolation(
                        path=_display_path(fixture_path),
                        message=f"file is {size} bytes; limit is {max_bytes} bytes",
                    )
                )

            content = fixture_path.read_text(encoding="utf-8", errors="replace")
            for literal in FORBIDDEN_LITERAL:
                if literal in content:
                    violations.append(
                        PrivacyViolation(
                            path=_display_path(fixture_path),
                            message=f"contains forbidden literal `{literal}`",
                        )
                    )
            for pattern in FORBIDDEN_REGEX:
                if pattern.search(content):
                    violations.append(
                        PrivacyViolation(
                            path=_display_path(fixture_path),
                            message=f"matches forbidden pattern `{pattern.pattern}`",
                        )
                    )
    return tuple(violations)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan synthetic plan/parser fixtures for private live-data leaks.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[FIXTURE_ROOT],
        help="Fixture file or directory paths to scan.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=MAX_FIXTURE_BYTES,
        help="Maximum allowed fixture file size.",
    )
    args = parser.parse_args(argv)

    violations = audit_paths(args.paths, max_bytes=args.max_bytes)
    if violations:
        print("Fixture privacy check failed:")
        for violation in violations:
            print(f"- {violation.path}: {violation.message}")
        return 1

    scanned_count = sum(1 for path in args.paths for _ in _iter_fixture_files(path))
    print(f"Fixture privacy check passed: scanned {scanned_count} fixture file(s).")
    return 0


def _iter_fixture_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if _is_fixture_file(path):
            yield path
        return

    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and _is_fixture_file(candidate):
            yield candidate


def _is_fixture_file(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return False
    return path.suffix not in SKIPPED_SUFFIXES


def _display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


if __name__ == "__main__":
    raise SystemExit(main())
