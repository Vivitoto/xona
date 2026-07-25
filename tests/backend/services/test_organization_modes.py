from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.actors import ActorOutputPlan
from backend.app.schemas.assets import MaterializedAsset, MaterializedAssetSet
from backend.app.schemas.media import MediaScanItem, MediaSidecarScanItem
from backend.app.schemas.operations import GeneratedArtifact
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.organizer_plans import OrganizerPlanService
from backend.app.services.storage_roots import StorageRootService


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _media_item(path: Path, *, identity: str, multipart_index: int | None = None) -> MediaScanItem:
    stat = path.stat()
    sidecar = path.with_suffix(".srt")
    return MediaScanItem(
        path=path,
        group_key="sample",
        multipart_index=multipart_index,
        identity=identity,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sidecars=[MediaSidecarScanItem(path=sidecar, kind="subtitle")],
    )


@pytest.mark.parametrize(
    ("mode", "media_operation"),
    [
        ("preview", "preview"),
        ("in_place", "rename"),
        ("move", "move"),
        ("copy", "copy"),
        ("hardlink", "hardlink"),
        ("symlink", "symlink"),
    ],
)
def test_modes_preserve_grouped_files_assets_and_actor_outputs(
    tmp_path: Path,
    mode: str,
    media_operation: str,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = incoming if mode == "in_place" else root / "organized"
    part1 = _write(incoming / "sample cd1.mkv", b"part-one")
    part2 = _write(incoming / "sample cd2.mkv", b"part-two")
    _write(incoming / "sample cd1.srt", b"subtitle-one")
    _write(incoming / "sample cd2.srt", b"subtitle-two")
    poster_cache = _write(root / "cache" / "poster.jpg", b"poster")
    actor_cache = _write(root / "cache" / "actor.jpg", b"actor")
    destination.mkdir(parents=True, exist_ok=True)
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            folder_path = "" if mode == "in_place" else "Studio/Sample"
            movie_root = destination if mode == "in_place" else destination / "Studio" / "Sample"
            plan = OrganizerPlanService(
                session,
                StorageRootService(settings, session),
            ).create_plan(
                mode=mode,
                media_items=[
                    _media_item(part1, identity="inode:1:1", multipart_index=1),
                    _media_item(part2, identity="inode:1:2", multipart_index=2),
                ],
                destination_root=destination,
                template_preview=TemplatePreview(
                    folder_path=folder_path,
                    filename="XC-001 - Renamed.mkv",
                    validation_errors=[],
                    warnings=[],
                ),
                materialized_assets=MaterializedAssetSet(
                    assets=[
                        MaterializedAsset(
                            kind="poster",
                            relative_path="poster.jpg",
                            source_url=None,
                            cache_path=poster_cache,
                            content_type="image/jpeg",
                            size_bytes=len(b"poster"),
                            sha256=_sha256(b"poster"),
                        )
                    ]
                ),
                generated_artifacts=[
                    GeneratedArtifact(
                        relative_path="XC-001 - Renamed.nfo",
                        content_text="<movie />",
                        artifact_type="nfo",
                    )
                ],
                actor_output_plans=[
                    ActorOutputPlan(
                        operation="copy",
                        source_path=actor_cache,
                        destination_path=movie_root / ".actors" / "Actor.jpg",
                        relative_path=Path(".actors") / "Actor.jpg",
                        destination_inside_root=True,
                        actor_name="Actor",
                    )
                ],
            )

            media_steps = [step for step in plan.steps if step.category == "media"]
            sidecar_steps = [step for step in plan.steps if step.sidecar]
            asset_steps = [step for step in plan.steps if step.materialized_asset]
            actor_steps = [step for step in plan.steps if step.actor_output]
            generated_step = next(step for step in plan.steps if step.generated_artifact)

            assert [step.operation for step in media_steps] == [media_operation, media_operation]
            assert len(sidecar_steps) == 2
            assert len(asset_steps) == 1
            assert len(actor_steps) == 1
            assert generated_step.target_path == movie_root / "XC-001 - Renamed.nfo"
            assert plan.source_snapshot[0].sha256 == _sha256(b"part-one")
            assert all(step.target_path is not None for step in plan.steps)
            assert any("part01" in str(step.target_path) for step in media_steps)
            assert any("part02" in str(step.target_path) for step in media_steps)

            if mode == "preview":
                assert all(step.destructive is False for step in plan.steps)
                assert {"move", "rename", "remove"} & {
                    step.operation for step in plan.steps
                } == set()
            if mode == "in_place":
                assert {step.target_path.parent for step in media_steps} == {incoming}
                assert generated_step.target_path.parent == incoming
    finally:
        engine.dispose()
