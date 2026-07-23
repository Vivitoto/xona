import asyncio

import httpx
from backend.app.main import create_app


def test_healthz_returns_exact_ok_status() -> None:
    async def run() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()),
            base_url="http://testserver",
        ) as client:
            return await client.get("/healthz")

    response = asyncio.run(run())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
