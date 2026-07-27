#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Sequence
from urllib.parse import quote, urlsplit

if __package__:
    from .disposable_smoke import (
        SmokeSafetyError,
        canonicalize_path,
        cleanup_disposable_root,
        create_disposable_root,
        validate_disposable_root,
    )
else:  # pragma: no cover - exercised by direct script execution.
    from disposable_smoke import (  # type: ignore[no-redef]
        SmokeSafetyError,
        canonicalize_path,
        cleanup_disposable_root,
        create_disposable_root,
        validate_disposable_root,
    )


ENABLE_ENV = "XONA_REAL_XCHINA_SMOKE"
ENABLE_VALUE = "1"
FLARESOLVERR_URL_ENV = "XONA_REAL_XCHINA_FLARESOLVERR_URL"
QUERY_ENV = "XONA_REAL_XCHINA_QUERY"
PROXY_URL_ENV = "XONA_REAL_XCHINA_PROXY_URL"
BASE_URL_ENV = "XONA_REAL_XCHINA_BASE_URL"
DEFAULT_XCHINA_BASE_URL = "https://xchina.co"


@dataclass(frozen=True)
class RealSmokeConfig:
    enabled: bool
    flaresolverr_url: str | None = None
    query: str | None = None
    proxy_url: str | None = None
    base_url: str = DEFAULT_XCHINA_BASE_URL


@dataclass(frozen=True)
class RealSmokeResult:
    status: str
    enabled: bool
    read_only: bool
    organized_files: int
    result_count: int
    disposable_root: Path | None = None

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["disposable_root"] = str(self.disposable_root) if self.disposable_root else None
        return payload


SearchRunner = Callable[[RealSmokeConfig], Awaitable[Sequence[object]] | Sequence[object]]


def config_from_env(environ: Mapping[str, str]) -> RealSmokeConfig:
    opt_in = environ.get(ENABLE_ENV)
    if opt_in is None or opt_in == "":
        return RealSmokeConfig(enabled=False)
    if opt_in != ENABLE_VALUE:
        raise SmokeSafetyError(f"{ENABLE_ENV} must be set to {ENABLE_VALUE!r} to run")

    endpoint = _required_env(environ, FLARESOLVERR_URL_ENV)
    query = _required_env(environ, QUERY_ENV)
    _validate_http_url(endpoint, FLARESOLVERR_URL_ENV)
    base_url = environ.get(BASE_URL_ENV, DEFAULT_XCHINA_BASE_URL).strip()
    _validate_http_url(base_url, BASE_URL_ENV)
    proxy_url = environ.get(PROXY_URL_ENV)
    if proxy_url:
        _validate_http_url(proxy_url, PROXY_URL_ENV)
    return RealSmokeConfig(
        enabled=True,
        flaresolverr_url=endpoint,
        query=query,
        proxy_url=proxy_url or None,
        base_url=base_url.rstrip("/"),
    )


def validate_real_smoke_path(
    path: Path | str,
    *,
    disposable_root: Path | str,
    require_exists: bool = True,
) -> Path:
    root = validate_disposable_root(disposable_root)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = canonicalize_path(candidate, require_exists=require_exists)
    _reject_broad_or_home_path(resolved)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SmokeSafetyError(f"Real smoke path is outside generated disposable root: {resolved}") from exc
    return resolved


async def run_real_xchina_smoke_async(
    *,
    environ: Mapping[str, str],
    search_runner: SearchRunner | None = None,
    keep_root: bool = False,
) -> RealSmokeResult:
    config = config_from_env(environ)
    if not config.enabled:
        return RealSmokeResult(
            status="skipped",
            enabled=False,
            read_only=True,
            organized_files=0,
            result_count=0,
        )

    root = create_disposable_root()
    try:
        validate_real_smoke_path(root, disposable_root=root, require_exists=True)
        runner = search_runner or _search_xchina_read_only
        maybe_results = runner(config)
        if inspect.isawaitable(maybe_results):
            results = await maybe_results
        else:
            results = maybe_results
        return RealSmokeResult(
            status="passed",
            enabled=True,
            read_only=True,
            organized_files=0,
            result_count=len(tuple(results)),
            disposable_root=root,
        )
    finally:
        if not keep_root:
            cleanup_disposable_root(root)


def run_real_xchina_smoke(
    *,
    environ: Mapping[str, str],
    search_runner: SearchRunner | None = None,
    keep_root: bool = False,
) -> RealSmokeResult:
    return asyncio.run(
        run_real_xchina_smoke_async(
            environ=environ,
            search_runner=search_runner,
            keep_root=keep_root,
        )
    )


async def _search_xchina_read_only(config: RealSmokeConfig) -> Sequence[object]:
    from backend.app.integrations.flaresolverr import FlareSolverrClient
    from backend.app.integrations.xchina import parse_search_results

    assert config.flaresolverr_url is not None
    assert config.query is not None
    url = f"{config.base_url}/videos/keyword-{quote(config.query, safe='')}.html"
    async with FlareSolverrClient(
        config.flaresolverr_url,
        proxy_url=config.proxy_url,
        max_timeout_ms=30_000,
    ) as client:
        response = await client.request_get(url)
    return parse_search_results(response.text, base_url=config.base_url)


def _required_env(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if value is None or not value.strip():
        raise SmokeSafetyError(f"{name} is required when {ENABLE_ENV}={ENABLE_VALUE}")
    return value.strip()


def _validate_http_url(value: str, name: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SmokeSafetyError(f"{name} must be an absolute http(s) URL")


def _reject_broad_or_home_path(path: Path) -> None:
    broad_roots = {
        Path("/").resolve(strict=False),
        Path("/tmp").resolve(strict=False),
        Path("/home").resolve(strict=False),
        Path("/Users").resolve(strict=False),
    }
    if path in broad_roots:
        raise SmokeSafetyError(f"Real smoke refuses broad filesystem roots: {path}")
    home = Path.home().resolve(strict=False)
    try:
        path.relative_to(home)
    except ValueError:
        return
    raise SmokeSafetyError(f"Real smoke refuses home-directory paths: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run opt-in read-only real xchina smoke.")
    parser.add_argument(
        "--keep-root",
        action="store_true",
        help="Leave the generated /tmp/xona-smoke-* root in place for inspection.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_real_xchina_smoke(environ=dict(__import__("os").environ), keep_root=args.keep_root)
    except SmokeSafetyError as exc:
        print(f"real xchina smoke safety error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - depends on external opt-in service state.
        print(f"real xchina smoke failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_json(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
