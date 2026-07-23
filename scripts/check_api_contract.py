#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
API_PREFIX = "/api"
SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx"})

_ROUTE_PARAM_RE = re.compile(r"\{[^/{}]+\}")
_TEMPLATE_INTERPOLATION_RE = re.compile(r"\$\{[^}]*\}")
_TRAILING_QUERY_INTERPOLATION_RE = re.compile(r"(?<!/)\{param\}.*$")


@dataclass(frozen=True)
class ApiPathReference:
    normalized_path: str
    raw_path: str
    file_path: Path
    line_number: int


@dataclass(frozen=True)
class ContractIssue:
    reference: ApiPathReference
    message: str


@dataclass(frozen=True)
class ContractReport:
    backend_paths: tuple[str, ...]
    references: tuple[ApiPathReference, ...]
    missing: tuple[ContractIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.missing

    @property
    def unique_frontend_paths(self) -> tuple[str, ...]:
        return tuple(sorted({reference.normalized_path for reference in self.references}))


def load_backend_openapi_paths() -> tuple[str, ...]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.app.main import create_app

    openapi = create_app().openapi()
    return tuple(sorted(path for path in openapi["paths"] if path.startswith(API_PREFIX)))


def audit_frontend_api_paths(
    frontend_src: Path = FRONTEND_SRC,
    *,
    backend_paths: Iterable[str] | None = None,
) -> ContractReport:
    route_paths = tuple(sorted(backend_paths if backend_paths is not None else load_backend_openapi_paths()))
    references = tuple(iter_frontend_api_references(frontend_src))
    first_reference_by_path = {
        reference.normalized_path: reference
        for reference in reversed(references)
    }

    missing = tuple(
        ContractIssue(
            reference=reference,
            message=f"{reference.normalized_path} is not registered in backend OpenAPI",
        )
        for reference in sorted(
            first_reference_by_path.values(),
            key=lambda item: (item.normalized_path, str(item.file_path), item.line_number),
        )
        if not any(route_matches(reference.normalized_path, route_path) for route_path in route_paths)
    )
    return ContractReport(
        backend_paths=route_paths,
        references=references,
        missing=missing,
    )


def iter_frontend_api_references(frontend_src: Path) -> Iterable[ApiPathReference]:
    root = frontend_src.resolve()
    for file_path in _iter_source_files(root):
        source = file_path.read_text(encoding="utf-8")
        for token in _iter_string_tokens(source):
            normalized_path = normalize_api_path(token.value)
            if normalized_path is None:
                continue
            if _ignore_reference(normalized_path, file_path):
                continue
            yield ApiPathReference(
                normalized_path=normalized_path,
                raw_path=token.value,
                file_path=_display_path(file_path),
                line_number=source.count("\n", 0, token.start) + 1,
            )


def normalize_api_path(raw_path: str) -> str | None:
    raw_path = raw_path.strip()
    if not raw_path.startswith(API_PREFIX):
        return None

    path = raw_path.replace("\\/", "/")
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = path.replace("${...}", "{param}")
    path = _TEMPLATE_INTERPOLATION_RE.sub("{param}", path)
    path = _TRAILING_QUERY_INTERPOLATION_RE.sub("", path)
    path = _ROUTE_PARAM_RE.sub("{}", path)
    path = re.sub(r"/+", "/", path)
    path = path.rstrip("/") if path != "/" else path
    if not path.startswith(API_PREFIX):
        return None
    return path or API_PREFIX


def normalize_route_template(route_path: str) -> str:
    path = route_path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return _ROUTE_PARAM_RE.sub("{}", path or "/")


def route_matches(frontend_path: str, route_path: str) -> bool:
    frontend_segments = _segments(normalize_route_template(frontend_path))
    route_segments = _segments(normalize_route_template(route_path))
    if len(frontend_segments) != len(route_segments):
        return False
    return all(_segment_matches(frontend, route) for frontend, route in zip(frontend_segments, route_segments))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare frontend /api path references with FastAPI OpenAPI routes.",
    )
    parser.add_argument(
        "--frontend-src",
        type=Path,
        default=FRONTEND_SRC,
        help="Frontend source file or directory to scan.",
    )
    args = parser.parse_args(argv)

    try:
        report = audit_frontend_api_paths(args.frontend_src)
    except Exception as exc:
        print(f"API contract check failed while loading contract data: {exc}", file=sys.stderr)
        return 1

    if report.missing:
        print("API contract check failed: frontend paths missing from backend OpenAPI.")
        for issue in report.missing:
            reference = issue.reference
            print(
                "- "
                f"{reference.normalized_path} at {reference.file_path}:{reference.line_number} "
                f"from `{_shorten(reference.raw_path)}`"
            )
        print("\nRegistered backend API routes:")
        for route_path in report.backend_paths:
            print(f"- {route_path}")
        return 1

    print(
        "API contract check passed: "
        f"{len(report.unique_frontend_paths)} frontend path pattern(s) matched "
        f"{len(report.backend_paths)} backend API route(s)."
    )
    return 0


@dataclass(frozen=True)
class _StringToken:
    value: str
    start: int


def _iter_source_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.suffix in SOURCE_SUFFIXES:
            yield root
        return

    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            yield path


def _iter_string_tokens(source: str) -> Iterable[_StringToken]:
    index = 0
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if char == "/" and next_char == "/":
            index = _skip_line_comment(source, index)
            continue
        if char == "/" and next_char == "*":
            index = _skip_block_comment(source, index)
            continue
        if char in {"'", '"'}:
            start = index
            value, index = _read_quoted_string(source, index)
            yield _StringToken(value=value, start=start)
            continue
        if char == "`":
            start = index
            value, index = _read_template_string(source, index)
            yield _StringToken(value=value, start=start)
            continue
        index += 1


def _read_quoted_string(source: str, start: int) -> tuple[str, int]:
    quote = source[start]
    index = start + 1
    value: list[str] = []
    while index < len(source):
        char = source[index]
        if char == "\\":
            if index + 1 < len(source):
                value.append(source[index + 1])
                index += 2
                continue
        if char == quote:
            return "".join(value), index + 1
        value.append(char)
        index += 1
    return "".join(value), index


def _read_template_string(source: str, start: int) -> tuple[str, int]:
    index = start + 1
    value: list[str] = []
    while index < len(source):
        char = source[index]
        if char == "\\":
            if index + 1 < len(source):
                value.append(char)
                value.append(source[index + 1])
                index += 2
                continue
        if char == "`":
            return "".join(value), index + 1
        if char == "$" and index + 1 < len(source) and source[index + 1] == "{":
            value.append("${...}")
            index = _skip_template_expression(source, index + 2)
            continue
        value.append(char)
        index += 1
    return "".join(value), index


def _skip_template_expression(source: str, start: int) -> int:
    depth = 1
    index = start
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if char in {"'", '"'}:
            index = _skip_quoted_string(source, index)
            continue
        if char == "`":
            index = _skip_template_string(source, index)
            continue
        if char == "/" and next_char == "/":
            index = _skip_line_comment(source, index)
            continue
        if char == "/" and next_char == "*":
            index = _skip_block_comment(source, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def _skip_quoted_string(source: str, start: int) -> int:
    quote = source[start]
    index = start + 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return index


def _skip_template_string(source: str, start: int) -> int:
    index = start + 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "`":
            return index + 1
        if char == "$" and index + 1 < len(source) and source[index + 1] == "{":
            index = _skip_template_expression(source, index + 2)
            continue
        index += 1
    return index


def _skip_line_comment(source: str, start: int) -> int:
    newline = source.find("\n", start + 2)
    return len(source) if newline == -1 else newline + 1


def _skip_block_comment(source: str, start: int) -> int:
    end = source.find("*/", start + 2)
    return len(source) if end == -1 else end + 2


def _segments(path: str) -> tuple[str, ...]:
    return tuple(segment for segment in path.strip("/").split("/") if segment)


def _segment_matches(frontend_segment: str, route_segment: str) -> bool:
    return (
        frontend_segment == route_segment
        or frontend_segment == "{}"
        or route_segment == "{}"
    )


def _ignore_reference(normalized_path: str, file_path: Path) -> bool:
    if normalized_path != "/api/e2e" and not normalized_path.startswith("/api/e2e/"):
        return False

    lower_parts = {part.lower() for part in file_path.parts}
    return bool({"e2e", "test", "tests"} & lower_parts) or ".test." in file_path.name


def _display_path(file_path: Path) -> Path:
    try:
        return file_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return file_path


def _shorten(value: str, limit: int = 100) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
