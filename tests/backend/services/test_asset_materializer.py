from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import AssetMaterialization
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.integrations.xchina import FetchedAsset
from backend.app.schemas.assets import AssetMaterializationPolicy, LogicalAsset, AssetSelection
from backend.app.services.asset_materializer import AssetMaterializer


class FakeAssetAdapter:
    def __init__(self, responses: dict[str, FetchedAsset]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    async def fetch_asset(self, url: str) -> FetchedAsset:
        self.urls.append(url)
        return self.responses[url]


def _database(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def test_materializes_movie_and_actor_assets_and_reuses_verified_cache(tmp_path: Path) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        selection = AssetSelection(
            assets=[
                LogicalAsset(
                    kind="poster",
                    relative_path="poster.jpg",
                    source_url="https://images.example.test/poster.jpg",
                    required=True,
                ),
                LogicalAsset(
                    kind="actor_portrait",
                    relative_path=".actors/Actor One.jpg",
                    source_url="https://images.example.test/actor-one.jpg",
                    actor_name="Actor One",
                    actor_source_id="ACT-001",
                ),
            ]
        )
        adapter = FakeAssetAdapter(
            {
                "https://images.example.test/poster.jpg": FetchedAsset(
                    url="https://images.example.test/poster.jpg",
                    content=b"poster-bytes",
                    content_type="image/jpeg",
                ),
                "https://images.example.test/actor-one.jpg": FetchedAsset(
                    url="https://images.example.test/actor-one.jpg",
                    content=b"actor-bytes",
                    content_type="image/jpeg",
                ),
            }
        )

        with sessionmaker() as session:
            materializer = AssetMaterializer(adapter, settings.config_dir, session=session)
            first = asyncio.run(
                materializer.materialize(selection, AssetMaterializationPolicy(strict=True))
            )
            second = asyncio.run(
                materializer.materialize(selection, AssetMaterializationPolicy(strict=True))
            )

            assert first.failed is False
            assert second.failed is False
            assert adapter.urls == [
                "https://images.example.test/poster.jpg",
                "https://images.example.test/actor-one.jpg",
            ]
            poster = first.by_relative_path("poster.jpg")
            actor = first.by_relative_path(".actors/Actor One.jpg")
            assert poster is not None
            assert actor is not None
            assert poster.cache_path.read_bytes() == b"poster-bytes"
            assert actor.cache_path.read_bytes() == b"actor-bytes"
            assert settings.config_dir / "asset-cache" in poster.cache_path.parents
            assert settings.config_dir / "actor-cache" in actor.cache_path.parents
            assert poster.sha256 == hashlib.sha256(b"poster-bytes").hexdigest()
            assert actor.size_bytes == len(b"actor-bytes")
            assert session.query(AssetMaterialization).count() == 2
    finally:
        engine.dispose()


def test_lenient_records_missing_required_assets_without_failing(tmp_path: Path) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        selection = AssetSelection(
            assets=[
                LogicalAsset(
                    kind="poster",
                    relative_path="poster.jpg",
                    source_url=None,
                    required=True,
                    missing_reason="missing_source_url",
                )
            ]
        )
        with sessionmaker() as session:
            result = asyncio.run(
                AssetMaterializer(
                    FakeAssetAdapter({}), settings.config_dir, session=session
                ).materialize(selection, AssetMaterializationPolicy(strict=False))
            )

            assert result.failed is False
            assert [(item.relative_path, item.reason) for item in result.missing] == [
                ("poster.jpg", "missing_source_url")
            ]
            assert result.assets == []
    finally:
        engine.dispose()


def test_strict_materializer_sniffs_extensionless_images_and_rejects_html(
    tmp_path: Path,
) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        selection = AssetSelection(
            assets=[
                LogicalAsset(
                    kind="poster",
                    relative_path="poster.jpg",
                    source_url="https://images.example.test/poster",
                    required=True,
                ),
                LogicalAsset(
                    kind="fanart",
                    relative_path="fanart.jpg",
                    source_url="https://images.example.test/fanart",
                    required=True,
                ),
            ]
        )
        adapter = FakeAssetAdapter(
            {
                "https://images.example.test/poster": FetchedAsset(
                    url="https://images.example.test/poster",
                    content=b"\xff\xd8\xff\xe0poster-bytes",
                    content_type="",
                ),
                "https://images.example.test/fanart": FetchedAsset(
                    url="https://images.example.test/fanart",
                    content=b"<html><body>not an image</body></html>",
                    content_type="image/jpeg",
                ),
            }
        )

        with sessionmaker() as session:
            result = asyncio.run(
                AssetMaterializer(adapter, settings.config_dir, session=session).materialize(
                    selection,
                    AssetMaterializationPolicy(strict=True),
                )
            )

            assert result.failed is True
            poster = result.by_relative_path("poster.jpg")
            assert poster is not None
            assert poster.content_type == "image/jpeg"
            assert [(item.relative_path, item.reason) for item in result.missing] == [
                ("fanart.jpg", "content_type_not_allowed")
            ]
    finally:
        engine.dispose()
