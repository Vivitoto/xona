from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.api.auth import authenticated_username, router as auth_router
from backend.app.api.health import router as health_router
from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations

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
        yield

    app = FastAPI(title="Xona", lifespan=lifespan)
    app.state.settings = settings

    @app.middleware("http")
    async def authenticate_api_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if settings.auth_enabled and request.url.path.startswith("/api/"):
            if request.method.upper() in UNSAFE_API_METHODS and not _has_same_origin(
                request
            ):
                return JSONResponse(
                    {"detail": "Same-origin request required"},
                    status_code=403,
                )

            if request.url.path not in AUTH_ENDPOINT_PATHS:
                username = authenticated_username(request, settings)
                if username is None:
                    return JSONResponse(
                        {"detail": "Authentication required"},
                        status_code=401,
                    )

        return await call_next(request)

    app.include_router(health_router)
    app.include_router(auth_router)

    return app


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
