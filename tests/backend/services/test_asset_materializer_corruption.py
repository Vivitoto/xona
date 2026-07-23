from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
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


def test_refuses_corrupted_cached_files_without_refetching(tmp_path: Path) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        selection = AssetSelection(
            assets=[
                LogicalAsset(
                    kind="poster",
                    relative_path="poster.jpg",
                    source_url="https://images.example.test/poster.jpg",
                    required=True,
                )
            ]
        )
        adapter = FakeAssetAdapter(
            {
                "https://images.example.test/poster.jpg": FetchedAsset(
                    url="https://images.example.test/poster.jpg",
                    content=b"poster-bytes",
                    content_type="image/jpeg",
                )
            }
        )

        with sessionmaker() as session:
            materializer = AssetMaterializer(adapter, settings.config_dir, session=session)
            first = asyncio.run(
                materializer.materialize(selection, AssetMaterializationPolicy(strict=True))
            )
            first.assets[0].cache_path.write_bytes(b"corrupt")

            second = asyncio.run(
                materializer.materialize(selection, AssetMaterializationPolicy(strict=True))
            )

            assert adapter.urls == ["https://images.example.test/poster.jpg"]
            assert second.failed is True
            assert [(item.relative_path, item.reason) for item in second.missing] == [
                ("poster.jpg", "cache_integrity_failed")
            ]
    finally:
        engine.dispose()


def test_rejects_disallowed_content_types_and_oversized_downloads(tmp_path: Path) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        selection = AssetSelection(
            assets=[
                LogicalAsset(
                    kind="poster",
                    relative_path="poster.jpg",
                    source_url="https://images.example.test/poster.txt",
                    required=True,
                ),
                LogicalAsset(
                    kind="fanart",
                    relative_path="fanart.jpg",
                    source_url="https://images.example.test/fanart.jpg",
                    required=True,
                ),
            ]
        )
        adapter = FakeAssetAdapter(
            {
                "https://images.example.test/poster.txt": FetchedAsset(
                    url="https://images.example.test/poster.txt",
                    content=b"text",
                    content_type="text/plain",
                ),
                "https://images.example.test/fanart.jpg": FetchedAsset(
                    url="https://images.example.test/fanart.jpg",
                    content=b"too-large",
                    content_type="image/jpeg",
                ),
            }
        )

        with sessionmaker() as session:
            result = asyncio.run(
                AssetMaterializer(adapter, settings.config_dir, session=session).materialize(
                    selection,
                    AssetMaterializationPolicy(strict=True, max_bytes=4),
                )
            )

            assert result.failed is True
            assert [item.reason for item in result.missing] == [
                "content_type_not_allowed",
                "download_too_large",
            ]
    finally:
        engine.dispose()
