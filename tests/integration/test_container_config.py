from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_dockerfile_builds_frontend_and_installs_backend_package() -> None:
    dockerfile = _read("Dockerfile")

    assert "FROM node:22-bookworm-slim AS frontend-build" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "python -m pip install --no-cache-dir -r constraints.txt" in dockerfile
    assert "COPY backend ./backend" in dockerfile
    assert "COPY --from=frontend-build /build/frontend/dist /app/static" in dockerfile
    assert "ENTRYPOINT [\"/usr/local/bin/xona-entrypoint\"]" in dockerfile
    assert (
        'CMD ["uvicorn", "backend.app.main:create_app", "--factory", "--host", '
        '"0.0.0.0", "--port", "8732"]'
    ) in dockerfile


def test_compose_defines_app_service_ports_and_mounts_without_storage_roots_env() -> None:
    compose = _read("docker-compose.yml")

    assert "  app:" in compose
    assert '"${XONA_PORT:-8732}:8732"' in compose
    assert 'PUID: "${PUID:-1000}"' in compose
    assert 'PGID: "${PGID:-1000}"' in compose
    assert "STORAGE_ROOTS" not in compose
    assert '"${CONFIG_ROOT:-./config}:/config"' in compose
    assert '"${MEDIA_ROOT:-./media}:/media"' in compose


def test_healthcheck_uses_loopback_healthz_endpoint() -> None:
    healthcheck = _read("docker/healthcheck.py")
    dockerfile = _read("Dockerfile")
    compose = _read("docker-compose.yml")

    assert 'HEALTHCHECK_URL = "http://127.0.0.1:8732/healthz"' in healthcheck
    assert 'CMD ["python", "/usr/local/bin/xona-healthcheck.py"]' in dockerfile
    assert 'test: ["CMD", "python", "/usr/local/bin/xona-healthcheck.py"]' in compose


def test_env_example_uses_redacted_local_defaults() -> None:
    env_example = _read(".env.example")

    assert "XONA_PORT=8732" in env_example
    assert "PUID=1000" in env_example
    assert "PGID=1000" in env_example
    assert "STORAGE_ROOTS=" not in env_example
    assert "API_KEY=" not in env_example
    assert "PASSWORD=" not in env_example
    assert "COOKIE=" not in env_example


def test_fastapi_serves_production_spa_without_api_fallback(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        '<div id="root"></div><script src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('xona');", encoding="utf-8")

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        app = create_app(
            Settings(config_dir=tmp_path / "config"),
            static_dir=static_dir,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return (
                await client.get("/"),
                await client.get("/manual/review/123"),
                await client.get("/api/not-a-real-route"),
            )

    root_response, spa_response, api_response = asyncio.run(run())

    assert root_response.status_code == 200
    assert "/assets/app.js" in root_response.text
    assert spa_response.status_code == 200
    assert "/assets/app.js" in spa_response.text
    assert api_response.status_code == 404
