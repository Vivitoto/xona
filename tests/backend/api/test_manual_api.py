from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

import backend.app.api.manual as manual_api
from backend.app.core.settings import Settings
from backend.app.integrations.xchina import FetchedAsset
from backend.app.main import create_app
from backend.app.schemas.source import SourceActorRef, SourceAsset, SourceSearchResult, SourceVideoDetail
from backend.app.services.settings_store import SettingsStore


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


class FailingSearchXChina:
    async def search(self, query: str) -> list[SourceSearchResult]:
        raise RuntimeError("FlareSolverr request failed")

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:  # pragma: no cover
        raise AssertionError("not used in this test")


class FakeImageAsset:
    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.content_type = content_type

    async def fetch_asset(self, url: str) -> FetchedAsset:
        return FetchedAsset(url=url, content=self.content, content_type=self.content_type)


class FakeStoredSettingsFlareSolverr:
    instances: list["FakeStoredSettingsFlareSolverr"] = []

    def __init__(self, url: str, *, proxy_url: str | None = None) -> None:
        self.url = url
        self.proxy_url = proxy_url
        self.closed = False
        self.instances.append(self)

    async def close(self) -> None:
        self.closed = True


class FakeStoredSettingsXChina:
    instances: list["FakeStoredSettingsXChina"] = []

    def __init__(
        self,
        flaresolverr: FakeStoredSettingsFlareSolverr,
        session,
        *,
        base_url: str = "https://www.xchina.co",
    ) -> None:
        self.flaresolverr = flaresolverr
        self.session = session
        self.base_url = base_url
        self.instances.append(self)

    async def search(self, query: str) -> list[SourceSearchResult]:
        assert query == "同学的妈妈"
        return [
            SourceSearchResult(
                source_candidate_id="XC-STORED",
                title="同学的妈妈",
                url="https://xchina.example.test/videos/xc-stored.html",
            )
        ]

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:  # pragma: no cover
        raise AssertionError("not used in this test")

    async def fetch_asset(self, url: str) -> FetchedAsset:  # pragma: no cover
        return FetchedAsset(url=url, content=b"proxied-image-bytes", content_type="image/webp")


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
    target_dir = destination / "Studio One" / "Sample Work Alpha"
    assert (target_dir / "XC-001 - Sample Work Alpha.mkv").is_file()
    assert (target_dir / "XC-001 - Sample Work Alpha.nfo").is_file()
    assert not (target_dir / "xchina-normalized.json").exists()


def test_manual_search_source_failure_returns_service_unavailable_without_500(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    (incoming / "Sample.Work.Alpha.mkv").write_bytes(b"movie-bytes")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        app.state.manual_search_adapter = FailingSearchXChina()
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
                    json={"job_id": job_id, "query": "Sample Work Alpha"},
                    headers={"Origin": ORIGIN},
                )
                job = await client.get(f"/api/manual/jobs/{job_id}")
                return {"scan": scan, "search": search, "job": job}

    responses = asyncio.run(run())

    assert responses["scan"].status_code == 200, responses["scan"].text
    assert responses["search"].status_code == 503, responses["search"].text
    assert responses["search"].json()["detail"]["error"] == "search_source_unavailable"
    assert responses["search"].json()["detail"]["reasons"] == ["search_source_unavailable"]
    assert responses["job"].json()["payload"]["manual"]["search_error"] == "search_source_unavailable"


def test_manual_search_uses_saved_xchina_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeStoredSettingsFlareSolverr.instances.clear()
    FakeStoredSettingsXChina.instances.clear()
    monkeypatch.setattr(manual_api, "FlareSolverrClient", FakeStoredSettingsFlareSolverr)
    monkeypatch.setattr(manual_api, "XChinaAdapter", FakeStoredSettingsXChina)

    root = tmp_path / "media"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    (incoming / "Sample.Work.Alpha.mkv").write_bytes(b"movie-bytes")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                SettingsStore(session).update_app_settings(
                    {
                        "xchina": {
                            "base_url": "https://mirror.xchina.test",
                            "flaresolverr_url": "http://solver:8191/v1",
                            "proxy_url": "http://proxy:8080",
                        }
                    }
                )
                session.commit()

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
                    json={"job_id": job_id, "query": "同学的妈妈"},
                    headers={"Origin": ORIGIN},
                )
                second_search = await client.post(
                    "/api/manual/search",
                    json={"job_id": job_id, "query": "同学的妈妈"},
                    headers={"Origin": ORIGIN},
                )
                return {"scan": scan, "search": search, "second_search": second_search}

    responses = asyncio.run(run())

    assert responses["scan"].status_code == 200, responses["scan"].text
    assert responses["search"].status_code == 200, responses["search"].text
    assert responses["second_search"].status_code == 200, responses["second_search"].text
    assert responses["search"].json()["candidates"][0]["title"] == "同学的妈妈"
    assert len(FakeStoredSettingsFlareSolverr.instances) == 1
    assert FakeStoredSettingsFlareSolverr.instances[0].url == "http://solver:8191/v1"
    assert FakeStoredSettingsFlareSolverr.instances[0].proxy_url == "http://proxy:8080"
    assert FakeStoredSettingsFlareSolverr.instances[0].closed is True
    assert len(FakeStoredSettingsXChina.instances) == 3
    assert all(
        adapter.flaresolverr is FakeStoredSettingsFlareSolverr.instances[0]
        for adapter in FakeStoredSettingsXChina.instances
    )
    assert FakeStoredSettingsXChina.instances[0].base_url == "https://mirror.xchina.test"


def test_manual_search_closes_shared_flaresolverr_client_when_saved_settings_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeStoredSettingsFlareSolverr.instances.clear()
    FakeStoredSettingsXChina.instances.clear()
    monkeypatch.setattr(manual_api, "FlareSolverrClient", FakeStoredSettingsFlareSolverr)
    monkeypatch.setattr(manual_api, "XChinaAdapter", FakeStoredSettingsXChina)

    root = tmp_path / "media"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    (incoming / "Sample.Work.Alpha.mkv").write_bytes(b"movie-bytes")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, object]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                SettingsStore(session).update_app_settings(
                    {
                        "xchina": {
                            "base_url": "https://mirror.xchina.test",
                            "flaresolverr_url": "http://solver:8191/v1",
                            "proxy_url": "http://proxy:8080",
                        }
                    }
                )
                session.commit()

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
                first_search = await client.post(
                    "/api/manual/search",
                    json={"job_id": job_id, "query": "同学的妈妈"},
                    headers={"Origin": ORIGIN},
                )

                with app.state.sessionmaker() as session:
                    SettingsStore(session).update_app_settings(
                        {
                            "xchina": {
                                "base_url": "https://mirror.xchina.test",
                                "flaresolverr_url": "http://solver:8191/v1",
                                "proxy_url": "http://proxy-2:8080",
                            }
                        }
                    )
                    session.commit()

                second_search = await client.post(
                    "/api/manual/search",
                    json={"job_id": job_id, "query": "同学的妈妈"},
                    headers={"Origin": ORIGIN},
                )
                return {
                    "first_search": first_search,
                    "second_search": second_search,
                    "first_closed_after_rotation": FakeStoredSettingsFlareSolverr.instances[0].closed,
                    "second_closed_before_shutdown": FakeStoredSettingsFlareSolverr.instances[1].closed,
                }

    responses = asyncio.run(run())

    assert responses["first_search"].status_code == 200, responses["first_search"].text
    assert responses["second_search"].status_code == 200, responses["second_search"].text
    assert len(FakeStoredSettingsFlareSolverr.instances) == 2
    assert FakeStoredSettingsFlareSolverr.instances[0].proxy_url == "http://proxy:8080"
    assert FakeStoredSettingsFlareSolverr.instances[1].proxy_url == "http://proxy-2:8080"
    assert responses["first_closed_after_rotation"] is True
    assert responses["second_closed_before_shutdown"] is False
    assert FakeStoredSettingsFlareSolverr.instances[1].closed is True


def test_manual_image_proxy_uses_saved_xchina_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeStoredSettingsFlareSolverr.instances.clear()
    FakeStoredSettingsXChina.instances.clear()
    monkeypatch.setattr(manual_api, "FlareSolverrClient", FakeStoredSettingsFlareSolverr)
    monkeypatch.setattr(manual_api, "XChinaAdapter", FakeStoredSettingsXChina)

    root = tmp_path / "media"
    root.mkdir()
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                SettingsStore(session).update_app_settings(
                    {
                        "xchina": {
                            "base_url": "https://media.xchina.test",
                            "flaresolverr_url": "http://solver:8191/v1",
                            "proxy_url": "http://proxy:8080",
                        }
                    }
                )
                session.commit()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get(
                    "/api/manual/image-proxy",
                    params={"url": "https://media.xchina.test/cover/demo.webp"},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert response.content == b"proxied-image-bytes"
    assert response.headers["content-type"] == "image/webp"
    assert FakeStoredSettingsFlareSolverr.instances
    assert FakeStoredSettingsFlareSolverr.instances[0].url == "http://solver:8191/v1"
    assert FakeStoredSettingsFlareSolverr.instances[0].proxy_url == "http://proxy:8080"
    assert FakeStoredSettingsFlareSolverr.instances[0].closed is True
    assert FakeStoredSettingsXChina.instances[0].base_url == "https://media.xchina.test"


def test_manual_image_proxy_rejects_untrusted_hosts(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> httpx.Response:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get(
                    "/api/manual/image-proxy",
                    params={"url": "https://example.com/cover.jpg"},
                )

    response = asyncio.run(run())

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("content", "expected_content_type"),
    [
        (b"\xff\xd8\xff\xe0jpeg-bytes", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\npng-bytes", "image/png"),
        (b"RIFF\x0c\x00\x00\x00WEBPwebp-bytes", "image/webp"),
    ],
)
def test_manual_image_proxy_sniffs_images_when_content_type_is_missing(
    tmp_path: Path,
    content: bytes,
    expected_content_type: str,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> httpx.Response:
        app = create_app(settings)
        app.state.manual_search_adapter = FakeImageAsset(content, "")
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get(
                    "/api/manual/image-proxy",
                    params={"url": "https://img.xchina.download/cover"},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert response.content == content
    assert response.headers["content-type"] == expected_content_type


def test_manual_image_proxy_rejects_html_masquerading_as_image(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> httpx.Response:
        app = create_app(settings)
        app.state.manual_search_adapter = FakeImageAsset(
            b"<!doctype html><html><body>blocked</body></html>",
            "image/jpeg",
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.get(
                    "/api/manual/image-proxy",
                    params={"url": "https://img.xchina.download/cover.jpg"},
                )

    response = asyncio.run(run())

    assert response.status_code == 415


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
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is False
    assert "unsafe_path" in response.json()["reasons"]
