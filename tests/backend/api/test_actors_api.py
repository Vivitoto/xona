from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.db.models import Actor, ActorMediaLink
from backend.app.integrations.xchina import FetchedAsset
from backend.app.main import create_app
from backend.app.schemas.metadata import MetadataRecordData
from backend.app.schemas.source import SourceActorDetail
from backend.app.services.metadata import persist_metadata_record
from backend.app.services.settings_store import SettingsStore


ORIGIN = "http://testserver"


class FakeXChina:
    async def fetch_actor_detail(self, url: str) -> SourceActorDetail:
        return SourceActorDetail(
            source_id="ACT-001",
            canonical_name="Actor One",
            aliases=["Alias New"],
            profile_url=url,
            portrait_url="https://images.example.test/actor.jpg",
            biography="Bio",
            associated_works=[
                {
                    "source_id": "XC-001",
                    "title": "Sample Work",
                    "url": "https://xchina.example.test/videos/xc-001.html",
                }
            ],
        )

    async def fetch_asset(self, url: str) -> FetchedAsset:
        return FetchedAsset(url=url, content=b"portrait-refresh", content_type="image/jpeg")


class FakeEmby:
    def __init__(self) -> None:
        self.uploaded: list[bytes] = []

    async def find_person(self, name: str):
        assert name == "Actor One"
        return {"Id": "person-1"}

    async def upload_person_portrait(self, person_id: str, portrait_bytes: bytes, *, content_type: str) -> None:
        assert person_id == "person-1"
        assert content_type == "image/jpeg"
        self.uploaded.append(portrait_bytes)


def test_actor_management_api(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)
    portrait = b"portrait"
    portrait_sha = hashlib.sha256(portrait).hexdigest()

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        fake_emby = FakeEmby()
        app.state.xchina_adapter = FakeXChina()
        app.state.emby_client = fake_emby
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                primary = Actor(
                    canonical_name="Actor One",
                    source="xchina",
                    source_id="ACT-001",
                    profile_url="https://xchina.example.test/models/actor-one.html",
                )
                duplicate = Actor(
                    canonical_name="Actor 1",
                    source="xchina",
                    source_id="ACT-ALT",
                )
                missing = Actor(canonical_name="Missing Portrait", source="xchina", source_id="ACT-M")
                session.add_all([primary, duplicate, missing])
                session.flush()
                record = persist_metadata_record(
                    session,
                    MetadataRecordData(
                        source="xchina",
                        xchina_id="XC-001",
                        source_url="https://xchina.example.test/videos/xc-001.html",
                        title="Sample Work",
                    ),
                )
                session.add(
                    ActorMediaLink(
                        actor_id=primary.id,
                        metadata_record_id=record.id,
                        source_id="XC-001",
                        title="Sample Work",
                    )
                )
                SettingsStore(session).update_app_settings(
                    {
                        "emby": {
                            "enabled": True,
                            "server_url": "http://emby.test",
                            "api_key": "emby-secret",
                        }
                    }
                )
                session.commit()
                primary_id = primary.id
                duplicate_id = duplicate.id

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                listed = await client.get("/api/actors?search=Actor")
                missing_response = await client.get("/api/actors?missing_image=true")
                aliases = await client.put(
                    f"/api/actors/{primary_id}/aliases",
                    json={"aliases": ["Alias One"]},
                    headers={"Origin": ORIGIN},
                )
                merge = await client.post(
                    f"/api/actors/{primary_id}/merge",
                    json={"duplicate_actor_id": duplicate_id},
                    headers={"Origin": ORIGIN},
                )
                portrait_response = await client.post(
                    f"/api/actors/{primary_id}/portrait",
                    content=portrait,
                    headers={
                        "Origin": ORIGIN,
                        "Content-Type": "image/jpeg",
                        "X-Content-SHA256": portrait_sha,
                    },
                )
                refresh = await client.post(
                    f"/api/actors/{primary_id}/refresh",
                    headers={"Origin": ORIGIN},
                )
                works = await client.get(f"/api/actors/{primary_id}/works")
                sync = await client.post(
                    f"/api/actors/{primary_id}/sync-emby",
                    headers={"Origin": ORIGIN},
                )
                detail = await client.get(f"/api/actors/{primary_id}")
                return {
                    "listed": listed,
                    "missing": missing_response,
                    "aliases": aliases,
                    "merge": merge,
                    "portrait": portrait_response,
                    "refresh": refresh,
                    "works": works,
                    "sync": sync,
                    "detail": detail,
                }

    responses = asyncio.run(run())

    assert responses["listed"].status_code == 200
    assert len(responses["listed"].json()["actors"]) >= 2
    assert "Missing Portrait" in responses["missing"].text
    assert responses["aliases"].json()["aliases"] == ["Alias One"]
    assert "Actor 1" in responses["merge"].text
    portrait_json = responses["portrait"].json()
    assert portrait_json["sha256"] == portrait_sha
    assert str(settings.config_dir / "actor-cache") in portrait_json["actor"]["portrait_cache_path"]
    assert "Alias New" in responses["refresh"].text
    assert responses["works"].json()["works"][0]["title"] == "Sample Work"
    assert responses["sync"].json()["uploaded_portrait"] is True
    assert responses["detail"].json()["emby_person_id"] == "person-1"
    assert "emby-secret" not in responses["sync"].text
