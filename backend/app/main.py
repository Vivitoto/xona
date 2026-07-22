from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.core.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Xona")
    app.state.settings = settings
    app.include_router(health_router)
    return app
