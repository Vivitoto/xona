from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        run_migrations(settings=settings)
        yield

    app = FastAPI(title="Xona", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    return app
