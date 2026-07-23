import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextlib import suppress
from urllib.parse import urlsplit

from fastapi import FastAPI
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


def create_app(settings: Settings | None = None) -> FastAPI:
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

    return app


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
