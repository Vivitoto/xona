from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.integrations.xchina import FetchedAsset
from backend.app.main import create_app
from backend.app.schemas.source import SourceActorRef, SourceAsset, SourceSearchResult, SourceVideoDetail


ORIGIN = "http://testserver"


class FakeXChina:
    async def search(self, query: str) -> list[SourceSearchResult]:
        assert "Sample Work" in query
        return [
            SourceSearchResult(
                source_candidate_id="XC-001",
                title="Sample Work Alpha",
                url="https://xchina.example.test/videos/xc-001.html",
                release_date="2026-01-02",
                thumbnail_url="https://images.example.test/thumb.jpg",
                actors=[SourceActorRef(name="Actor One", source_id="ACT-001")],
                studio="Studio One",
                series="Series One",
            )
        ]

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        assert url.endswith("xc-001.html")
        return SourceVideoDetail(
            source_id="XC-001",
            source_url=url,
            title="Sample Work Alpha",
            original_title="Sample Work Alpha Original",
            plot="Synthetic plot.",
            release_date="2026-01-02",
            runtime_minutes=90,
            studio="Studio One",
            series="Series One",
            actors=[SourceActorRef(name="Actor One", source_id="ACT-001")],
            poster=SourceAsset(url="https://images.example.test/poster.jpg", kind="poster"),
            fanart=SourceAsset(url="https://images.example.test/fanart.jpg", kind="fanart"),
            is_complete=True,
        )

    async def fetch_asset(self, url: str) -> FetchedAsset:
        return FetchedAsset(url=url, content=f"bytes:{url}".encode(), content_type="image/jpeg")


def test_manual_api_scan_search_select_preview_execute(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    source = incoming / "Sample.Work.Alpha.mkv"
    source.write_bytes(b"movie-bytes")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        app.state.manual_search_adapter = FakeXChina()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                scan = await client.post(
                    "/api/manual/scan",
                    json={"directory": str(incoming)},
                    headers={"Origin": ORIGIN},
                )
                job_id = scan.json()["jobs"][0]["job_id"]
                search = await client.post(
                    "/api/manual/search",
                    json={
                        "job_id": job_id,
                        "filename": source.name,
                        "normalized_query": "Sample Work Alpha",
                    },
                    headers={"Origin": ORIGIN},
                )
                candidate_id = search.json()["candidates"][0]["candidate_id"]
                select = await client.post(
                    f"/api/manual/jobs/{job_id}/select-candidate",
                    json={"candidate_id": candidate_id, "strict_assets": True},
                    headers={"Origin": ORIGIN},
                )
                preview = await client.post(
                    f"/api/manual/jobs/{job_id}/preview",
                    json={
                        "destination_root": str(destination),
                        "mode": "copy",
                        "folder_templates": ["{studio}", "{title}"],
                        "filename_template": "{xchina_id} - {title}",
                        "asset_policy": "strict",
                    },
                    headers={"Origin": ORIGIN},
                )
                plan_id = preview.json()["plan_id"]
                execute = await client.post(
                    f"/api/manual/plans/{plan_id}/execute",
                    json={"approved": True, "plan_version": 1},
                    headers={"Origin": ORIGIN},
                )
                job = await client.get(f"/api/manual/jobs/{job_id}")
                return {
                    "scan": scan,
                    "search": search,
                    "select": select,
                    "preview": preview,
                    "execute": execute,
                    "job": job,
                }

    responses = asyncio.run(run())

    assert responses["scan"].status_code == 200, responses["scan"].text
    assert responses["search"].json()["candidates"][0]["confidence_score"] > 0
    assert responses["select"].json()["accepted"] is True
    assert responses["preview"].status_code == 200, responses["preview"].text
    assert responses["preview"].json()["materialized_assets"]
    assert responses["execute"].json()["state"] == "completed"
    assert responses["job"].json()["state"] == "completed"
    assert (destination / "Studio One" / "Sample Work Alpha" / "XC-001 - Sample Work Alpha.mkv").is_file()


def test_manual_selection_refuses_unsafe_paths(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    (incoming / "Sample.Work.Alpha.mkv").write_bytes(b"movie-bytes")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> httpx.Response:
        app = create_app(settings)
        app.state.manual_search_adapter = FakeXChina()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                scan = await client.post(
                    "/api/manual/scan",
                    json={"directory": str(incoming)},
                    headers={"Origin": ORIGIN},
                )
                job_id = scan.json()["jobs"][0]["job_id"]
                search = await client.post(
                    "/api/manual/search",
                    json={"job_id": job_id, "normalized_query": "Sample Work Alpha"},
                    headers={"Origin": ORIGIN},
                )
                candidate_id = search.json()["candidates"][0]["candidate_id"]
                return await client.post(
                    f"/api/manual/jobs/{job_id}/select-candidate",
                    json={
                        "candidate_id": candidate_id,
                        "safety": {"unsafe_path": True},
                    },
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())
    assert response.status_code == 400
    assert "unsafe_path" in response.text
