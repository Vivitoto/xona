import asyncio
import mimetypes
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.api.auth import authenticated_username, router as auth_router
from backend.app.api.actors import router as actors_router
from backend.app.api.emby import router as emby_router
from backend.app.api.health import router as health_router
from backend.app.api.history import router as history_router
from backend.app.api.jobs import router as jobs_router
from backend.app.api.manual import router as manual_router
from backend.app.api.settings import router as settings_router
from backend.app.api.storage_roots import router as storage_roots_router
from backend.app.api.watch_rules import router as watch_rules_router
from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker

AUTH_ENDPOINT_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
}
UNSAFE_API_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
STATIC_DIR_ENV = "XONA_STATIC_DIR"


def create_app(
    settings: Settings | None = None,
    *,
    static_dir: str | Path | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        run_migrations(settings=settings)
        engine = create_engine_for_settings(settings)
        app.state.engine = engine
        app.state.sessionmaker = get_sessionmaker(engine)
        worker_task: asyncio.Task[None] | None = None
        monitor = None
        try:
            if settings.worker_enabled:
                from backend.app.services.worker import Worker

                app.state.worker = Worker(app.state.sessionmaker)
                worker_task = asyncio.create_task(app.state.worker.run_forever())
                app.state.worker_task = worker_task
            if settings.monitor_enabled:
                from backend.app.services.monitor import MonitorService

                monitor = MonitorService(settings, app.state.sessionmaker)
                monitor.start()
                app.state.monitor = monitor
            yield
        finally:
            if monitor is not None:
                monitor.stop()
            if worker_task is not None:
                app.state.worker.stop()
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task
            engine.dispose()

    app = FastAPI(title="Xona", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(ApiAuthMiddleware, settings=settings)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(storage_roots_router)
    app.include_router(watch_rules_router)
    app.include_router(manual_router)
    app.include_router(emby_router)
    app.include_router(jobs_router)
    app.include_router(history_router)
    app.include_router(settings_router)
    app.include_router(actors_router)

    mount_static_frontend(app, static_dir=static_dir)

    return app


def mount_static_frontend(
    app: FastAPI,
    *,
    static_dir: str | Path | None = None,
) -> None:
    static_path = _resolve_static_dir(static_dir)
    if static_path is None:
        return

    app.state.static_dir = static_path

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_frontend_root(request: Request) -> Response:
        return _static_frontend_response(
            static_path,
            request_path=request.url.path,
            frontend_path="",
        )

    @app.api_route(
        "/{frontend_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def serve_frontend_path(request: Request, frontend_path: str) -> Response:
        return _static_frontend_response(
            static_path,
            request_path=request.url.path,
            frontend_path=frontend_path,
        )


def _resolve_static_dir(static_dir: str | Path | None) -> Path | None:
    configured = static_dir if static_dir is not None else os.environ.get(STATIC_DIR_ENV)
    if configured is None or configured == "":
        return None

    path = Path(configured)
    if not path.is_dir():
        raise RuntimeError(f"Static frontend directory does not exist: {path}")
    if not (path / "index.html").is_file():
        raise RuntimeError(f"Static frontend index.html does not exist: {path}")

    return path


def _static_frontend_response(
    static_dir: Path,
    *,
    request_path: str,
    frontend_path: str,
) -> Response:
    if _is_api_path(request_path):
        raise HTTPException(status_code=404)

    file_path = _static_file_path(static_dir, frontend_path)
    if file_path is None:
        file_path = static_dir / "index.html"

    media_type, _ = mimetypes.guess_type(file_path.name)
    return Response(
        content=file_path.read_bytes(),
        media_type=media_type or "application/octet-stream",
    )


def _static_file_path(static_dir: Path, frontend_path: str) -> Path | None:
    if frontend_path in {"", "."}:
        return None

    relative_path = Path(frontend_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None

    root = static_dir.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    if candidate.is_dir():
        candidate = (candidate / "index.html").resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
    if candidate.is_file():
        return candidate
    return None


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class ApiAuthMiddleware:
    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self._app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if self._settings.auth_enabled and request.url.path.startswith("/api/"):
            response: Response | None = self._authorize(request)
            if response is not None:
                await response(scope, receive, send)
                return

        await self._app(scope, receive, send)

    def _authorize(self, request: Request) -> Response | None:
        if request.method.upper() in UNSAFE_API_METHODS and not _has_same_origin(
            request
        ):
            return JSONResponse(
                {"detail": "Same-origin request required"},
                status_code=403,
            )

        if request.url.path not in AUTH_ENDPOINT_PATHS:
            username = authenticated_username(request, self._settings)
            if username is None:
                return JSONResponse(
                    {"detail": "Authentication required"},
                    status_code=401,
                )

        return None


def _has_same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False

    origin_parts = urlsplit(origin)
    if not origin_parts.scheme or not origin_parts.hostname:
        return False

    try:
        origin_port = origin_parts.port or _default_port(origin_parts.scheme)
    except ValueError:
        return False

    request_port = request.url.port or _default_port(request.url.scheme)

    return (
        origin_parts.scheme.lower() == request.url.scheme.lower()
        and origin_parts.hostname.lower() == (request.url.hostname or "").lower()
        and origin_port == request_port
    )


def _default_port(scheme: str) -> int | None:
    return {"http": 80, "https": 443}.get(scheme.lower())
