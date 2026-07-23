from __future__ import annotations

from pathlib import Path

from backend.app.schemas.assets import MaterializedAsset
from backend.app.schemas.metadata import MetadataActor, MetadataRecordData
from backend.app.services.actors import plan_movie_actor_outputs


def _record() -> MetadataRecordData:
    return MetadataRecordData(
        source="xchina",
        xchina_id="XC-001",
        source_url="https://example.test/videos/sample-work-alpha.html",
        title="Sample Work Alpha",
        actors=[
            MetadataActor(name="Actor One", source_id="ACT-001"),
            MetadataActor(name="../Actor:Two", source_id="ACT-002"),
        ],
    )


def test_plans_per_movie_actor_outputs_without_writing_destinations(tmp_path: Path) -> None:
    cache_file = tmp_path / "config" / "actor-cache" / "xchina" / "ACT-001" / "actor.jpg"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"portrait")
    movie_root = tmp_path / "media" / "movie"
    movie_root.mkdir(parents=True)

    outputs = plan_movie_actor_outputs(
        _record(),
        [
            MaterializedAsset(
                kind="actor_portrait",
                relative_path=".actors/Actor One.jpg",
                source_url="https://images.example.test/actor-one.jpg",
                cache_path=cache_file,
                content_type="image/jpeg",
                size_bytes=8,
                sha256="sha",
                actor_name="Actor One",
                actor_source_id="ACT-001",
            )
        ],
        movie_root=movie_root,
        mode="hardlink",
    )

    assert len(outputs) == 1
    assert outputs[0].operation == "hardlink"
    assert outputs[0].source_path == cache_file
    assert outputs[0].relative_path == Path(".actors") / "Actor One.jpg"
    assert outputs[0].destination_path == movie_root / ".actors" / "Actor One.jpg"
    assert outputs[0].destination_inside_root is True
    assert not outputs[0].destination_path.exists()


def test_actor_output_sanitizes_names_and_supports_copy_and_symlink(tmp_path: Path) -> None:
    cache_file = tmp_path / "config" / "actor-cache" / "xchina" / "ACT-002" / "actor.jpg"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"portrait")

    for mode in ("copy", "symlink"):
        outputs = plan_movie_actor_outputs(
            _record(),
            [
                MaterializedAsset(
                    kind="actor_portrait",
                    relative_path=".actors/Actor_Two.jpg",
                    source_url="https://images.example.test/actor-two.jpg",
                    cache_path=cache_file,
                    content_type="image/jpeg",
                    size_bytes=8,
                    sha256="sha",
                    actor_name="../Actor:Two",
                    actor_source_id="ACT-002",
                )
            ],
            movie_root=tmp_path / "movie",
            mode=mode,
        )

        assert outputs[0].operation == mode
        assert outputs[0].relative_path == Path(".actors") / "Actor_Two.jpg"
        assert outputs[0].destination_inside_root is True
