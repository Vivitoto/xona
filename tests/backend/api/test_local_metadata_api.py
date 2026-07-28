from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from PIL import Image

from backend.app.core.settings import Settings
from backend.app.main import create_app
from backend.app.schemas.local_metadata import LocalVideoTechnicalInfo
from backend.app.services import local_metadata as local_metadata_service


ORIGIN = "http://testserver"


def test_local_metadata_api_analyze_and_nfo_preview_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    video = incoming / "site-prefix ABC123 [1080p] Local.Work.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    def fake_probe(path: Path) -> LocalVideoTechnicalInfo:
        return LocalVideoTechnicalInfo(
            path=path,
            size_bytes=video.stat().st_size,
            duration_seconds=125.2,
            width=1920,
            height=1080,
            video_codec="h264",
            audio_codec="aac",
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            bit_rate=5000000,
            fps=29.97,
        )

    monkeypatch.setattr(local_metadata_service, "probe_video", fake_probe)

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                analyze = await client.post(
                    "/api/local-metadata/analyze",
                    json={"video_path": str(video)},
                    headers={"Origin": ORIGIN},
                )
                nfo = await client.post(
                    "/api/local-metadata/nfo-preview",
                    json={
                        "metadata": {
                            "video_path": str(video),
                            "title": "Local Work",
                            "plot": "Local draft.",
                            "tags": ["local-generated", "unmatched"],
                        }
                    },
                    headers={"Origin": ORIGIN},
                )
                return {"analyze": analyze, "nfo": nfo}

    responses = asyncio.run(run())

    assert responses["analyze"].status_code == 200, responses["analyze"].text
    analyzed = responses["analyze"].json()
    assert analyzed["cleaned_title"] == "ABC123 Local Work"
    assert analyzed["default_organize_filename"] == "ABC123 Local Work"
    assert analyzed["technical"]["width"] == 1920
    assert analyzed["technical"]["duration_seconds"] == 125.2

    assert responses["nfo"].status_code == 200, responses["nfo"].text
    nfo = responses["nfo"].json()
    assert "<title>Local Work</title>" in nfo["xml_text"]
    assert '<uniqueid type="local" default="true">local-' in nfo["xml_text"]


def test_local_metadata_api_cover_preview_title_position_contract(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    video = incoming / "Local.Work.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    cache_root = settings.config_dir / "cache" / "local_metadata"
    frame = cache_root / "manual" / "frame.jpg"
    frame.parent.mkdir(parents=True)
    Image.new("RGB", (640, 360), (120, 84, 48)).save(frame)

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                valid = await client.post(
                    "/api/local-metadata/cover-preview",
                    json={
                        "video_path": str(video),
                        "title": "Local\nPoster",
                        "title_angle_degrees": -12,
                        "title_position_x_percent": 20,
                        "title_position_y_percent": 35,
                        "template": "simple_poster",
                        "title_font_id": "lxgw_wenkai",
                        "selected_frame_ids": ["manual/frame.jpg"],
                    },
                    headers={"Origin": ORIGIN},
                )
                invalid = await client.post(
                    "/api/local-metadata/cover-preview",
                    json={
                        "video_path": str(video),
                        "title": "Local Poster",
                        "title_position_x_percent": 101,
                        "template": "simple_poster",
                        "selected_frame_ids": ["manual/frame.jpg"],
                    },
                    headers={"Origin": ORIGIN},
                )
                return {"valid": valid, "invalid": invalid}

    responses = asyncio.run(run())

    assert responses["valid"].status_code == 200, responses["valid"].text
    preview = responses["valid"].json()
    assert preview["poster"]["kind"] == "poster"
    assert preview["fanart"]["kind"] == "fanart"
    assert preview["title_font_id"] == "lxgw_wenkai"
    assert preview["selected_frame_ids"] == ["manual/frame.jpg"]
    assert responses["invalid"].status_code == 422
