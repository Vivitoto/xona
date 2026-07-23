from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Actor, ActorMediaLink
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.integrations.xchina import parse_actor_detail
from backend.app.services.actors import ActorCacheService


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "xchina"


def _database(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def _actor_detail():
    return parse_actor_detail(
        (FIXTURE_ROOT / "actor_detail_sample.html").read_text(encoding="utf-8"),
        source_url="https://example.test/models/actor-one.html",
        base_url="https://example.test",
    )


def test_upserts_actor_records_and_missing_image_queries(tmp_path: Path) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            service = ActorCacheService(session, settings.config_dir)
            portrait_path = service.portrait_cache_path(
                source="xchina",
                source_id="ACT-001",
                name="Actor One",
                portrait_url="https://images.example.test/actor-one.jpg",
            )
            portrait_path.parent.mkdir(parents=True)
            portrait_path.write_bytes(b"portrait")

            actor = service.upsert_from_source(
                _actor_detail(),
                portrait_cache_path=portrait_path,
                portrait_sha256="sha",
                portrait_size_bytes=8,
                emby_person_id="emby-1",
            )
            session.commit()

            loaded = session.get(Actor, actor.id)
            assert loaded is not None
            assert loaded.canonical_name == "Actor One"
            assert loaded.source == "xchina"
            assert loaded.source_id == "ACT-001"
            assert loaded.profile_url == "https://example.test/models/actor-one.html"
            assert loaded.portrait_source_url == "https://images.example.test/actor-one.jpg"
            assert loaded.portrait_cache_path == str(portrait_path)
            assert loaded.biography == "Synthetic biography text for parser tests."
            assert loaded.profile_fields["Birthplace"] == "Example City"
            assert loaded.associated_works[0]["source_id"] == "XC-001"
            assert loaded.emby_person_id == "emby-1"
            assert {alias.alias for alias in loaded.aliases} == {
                "Alias One",
                "Sample Alias",
            }
            assert service.actors_missing_images() == []

            portrait_path.unlink()
            assert [item.id for item in service.actors_missing_images()] == [actor.id]
    finally:
        engine.dispose()


def test_actor_merge_preserves_aliases_links_and_portrait_metadata(tmp_path: Path) -> None:
    settings, engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            service = ActorCacheService(session, settings.config_dir)
            primary = Actor(canonical_name="Actor One", source="xchina", source_id="ACT-001")
            duplicate = Actor(
                canonical_name="Actor 1",
                source="xchina",
                source_id="ACT-ALT",
                portrait_cache_path=str(settings.config_dir / "actor-cache" / "portrait.jpg"),
                portrait_sha256="sha",
                portrait_size_bytes=12,
            )
            session.add_all([primary, duplicate])
            session.flush()
            service.add_alias(primary, "Primary Alias")
            service.add_alias(duplicate, "Duplicate Alias")
            session.add(
                ActorMediaLink(
                    actor_id=duplicate.id,
                    source_id="XC-001",
                    title="Sample Work Alpha",
                    source_url="https://example.test/videos/sample-work-alpha.html",
                )
            )
            session.flush()

            merged = service.merge(primary.id, duplicate.id)
            session.commit()

            assert merged.id == primary.id
            assert {alias.alias for alias in merged.aliases} == {
                "Primary Alias",
                "Duplicate Alias",
                "Actor 1",
            }
            assert merged.portrait_cache_path == duplicate.portrait_cache_path
            assert [link.actor_id for link in merged.media_links] == [primary.id]
            assert session.get(Actor, duplicate.id) is None
    finally:
        engine.dispose()
