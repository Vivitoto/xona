from fastapi import FastAPI

from backend.app.api.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Xona")
    app.include_router(health_router)
    return app
