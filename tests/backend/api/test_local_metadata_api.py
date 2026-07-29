from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

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
                            "studio": "Studio Local",
                            "actors": ["Actor Local"],
                            "technical": fake_probe(video).model_dump(mode="json"),
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
    assert "<fileinfo>" in nfo["xml_text"]
    assert "<width>1920</width>" in nfo["xml_text"]
    assert "<height>1080</height>" in nfo["xml_text"]
    assert "<codec>h264</codec>" in nfo["xml_text"]
    assert "<label>1080p</label>" in nfo["xml_text"]
    assert "<label>Actor Local</label>" in nfo["xml_text"]
    assert "<label>Studio Local</label>" in nfo["xml_text"]
    assert "<customrating>" not in nfo["xml_text"]
    assert "<countrycode>" not in nfo["xml_text"]
    assert "<mpaa>" not in nfo["xml_text"]
    assert "<num>" not in nfo["xml_text"]


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
    frame_dir = cache_root / "manual"
    frame_dir.mkdir(parents=True)
    selected_frame_ids: list[str] = []
    for index in range(1, 10):
        frame = frame_dir / f"frame-{index}.jpg"
        image = Image.new("RGB", (640, 360), (60 + index * 18, 45 + index * 14, 35 + index * 16))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 620, 340), outline=(255, 255, 255), width=5)
        for offset in range(0, 180, 45):
            draw.line((offset, index * 10, 640 - offset, 360 - index * 8), fill=(20, 20, 20), width=4)
            draw.line((640 - offset, 30 + offset, offset, 330 - offset), fill=(255, 240, 120), width=3)
        draw.ellipse((40 + index * 12, 80, 220 + index * 12, 260), outline=(255, 240, 120), width=4)
        image.save(frame)
        selected_frame_ids.append(f"manual/frame-{index}.jpg")

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
                        "selected_frame_ids": selected_frame_ids,
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
                        "selected_frame_ids": selected_frame_ids,
                    },
                    headers={"Origin": ORIGIN},
                )
                too_few = await client.post(
                    "/api/local-metadata/cover-preview",
                    json={
                        "video_path": str(video),
                        "title": "Local Poster",
                        "template": "simple_poster",
                        "selected_frame_ids": selected_frame_ids[:4],
                    },
                    headers={"Origin": ORIGIN},
                )
                return {"valid": valid, "invalid": invalid, "too_few": too_few}

    responses = asyncio.run(run())

    assert responses["valid"].status_code == 200, responses["valid"].text
    preview = responses["valid"].json()
    assert preview["poster"]["kind"] == "poster"
    assert preview["fanart"]["kind"] == "fanart"
    assert preview["thumb"]["kind"] == "thumb"
    assert preview["title_font_id"] == "lxgw_wenkai"
    assert preview["selected_frame_ids"] == selected_frame_ids
    assert responses["invalid"].status_code == 422
    assert responses["too_few"].status_code == 400
    assert responses["too_few"].json()["detail"]["error"] == "cover_generation_failed"
    assert responses["too_few"].json()["detail"]["reasons"] == [
        "nine_distinct_frames_required:4"
    ]
