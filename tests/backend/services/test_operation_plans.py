from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.db.models import OperationStep as OperationStepModel
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.actors import ActorOutputPlan
from backend.app.schemas.assets import MaterializedAsset, MaterializedAssetSet
from backend.app.schemas.media import MediaScanItem, MediaSidecarScanItem
from backend.app.schemas.operations import GeneratedArtifact
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.organizer_plans import (
    OperationPlanConflictError,
    OperationPlanSafetyError,
    OrganizerPlanService,
)
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


def _template(filename: str = "XC-001 - Sample.mkv") -> TemplatePreview:
    return TemplatePreview(
        folder_path="Studio/Sample",
        filename=filename,
        validation_errors=[],
        warnings=["truncated_filename"],
    )


def _media(video: Path, sidecar: Path) -> MediaScanItem:
    stat = video.stat()
    return MediaScanItem(
        path=video,
        group_key="sample",
        identity="inode:1:2",
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sidecars=[MediaSidecarScanItem(path=sidecar, kind="subtitle")],
    )


def test_persists_immutable_snapshot_with_sources_targets_hashes_and_artifacts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    video = _write(incoming / "sample.mkv", b"video-bytes")
    sidecar = _write(incoming / "sample.srt", b"subtitle-bytes")
    poster_cache = _write(root / "cache" / "poster.jpg", b"poster-bytes")
    actor_cache = _write(root / "cache" / "actor-one.jpg", b"actor-bytes")
    destination.mkdir(parents=True)
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            storage_roots = StorageRootService(settings, session)
            materialized = MaterializedAssetSet(
                assets=[
                    MaterializedAsset(
                        kind="poster",
                        relative_path="poster.jpg",
                        source_url="https://images.example.test/poster.jpg",
                        cache_path=poster_cache,
                        content_type="image/jpeg",
                        size_bytes=len(b"poster-bytes"),
                        sha256=_sha256(b"poster-bytes"),
                    )
                ]
            )
            actor_outputs = [
                ActorOutputPlan(
                    operation="copy",
                    source_path=actor_cache,
                    destination_path=destination
                    / "Studio"
                    / "Sample"
                    / ".actors"
                    / "Actor One.jpg",
                    relative_path=Path(".actors") / "Actor One.jpg",
                    destination_inside_root=True,
                    actor_name="Actor One",
                    actor_source_id="ACT-001",
                )
            ]
            generated = [
                GeneratedArtifact(
                    relative_path="XC-001 - Sample.nfo",
                    content_text="<movie><title>Sample</title></movie>",
                    artifact_type="nfo",
                    allow_replace_existing=True,
                )
            ]

            plan = OrganizerPlanService(session, storage_roots).create_plan(
                mode="copy",
                media_items=[_media(video, sidecar)],
                destination_root=destination,
                template_preview=_template(),
                materialized_assets=materialized,
                generated_artifacts=generated,
                actor_output_plans=actor_outputs,
            )
            session.commit()

            assert plan.conflicts == ()
            assert plan.safety_warnings[0].code == "truncated_filename"
            assert plan.source_snapshot[0].path == video
            assert plan.source_snapshot[0].sha256 == _sha256(b"video-bytes")
            assert plan.steps[0].source_path == video
            assert plan.steps[0].target_path == destination / "Studio" / "Sample" / "XC-001 - Sample.mkv"
            assert plan.steps[0].expected_size_bytes == len(b"video-bytes")
            assert plan.steps[0].sha256 == _sha256(b"video-bytes")
            assert any(step.sidecar for step in plan.steps)
            assert any(step.materialized_asset for step in plan.steps)
            assert any(step.actor_output for step in plan.steps)
            generated_step = next(step for step in plan.steps if step.generated_artifact)
            assert generated_step.operation == "write_generated"
            assert generated_step.target_path == (
                destination / "Studio" / "Sample" / "XC-001 - Sample.nfo"
            )
            assert generated_step.expected_size_bytes == len(
                b"<movie><title>Sample</title></movie>"
            )

            with pytest.raises(Exception):
                plan.steps[0].operation = "move"  # type: ignore[misc]

            persisted = session.query(OperationPlanModel).one()
            persisted_steps = session.query(OperationStepModel).all()
            assert persisted.plan_id == plan.plan_id
            assert persisted.plan_json["plan_id"] == plan.plan_id
            assert persisted.plan_json["steps"][0]["source_path"] == str(video)
            assert len(persisted_steps) == len(plan.steps)
    finally:
        engine.dispose()


def test_destination_collisions_fail_but_explicit_generated_replacements_are_allowed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    video = _write(incoming / "sample.mkv", b"video-bytes")
    sidecar = _write(incoming / "sample.srt", b"subtitle-bytes")
    target_dir = destination / "Studio" / "Sample"
    _write(target_dir / "XC-001 - Sample.mkv", b"existing-video")
    _write(target_dir / "Other.nfo", b"existing-metadata")
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            service = OrganizerPlanService(
                session,
                StorageRootService(settings, session),
            )
            with pytest.raises(OperationPlanConflictError) as exc_info:
                service.create_plan(
                    mode="copy",
                    media_items=[_media(video, sidecar)],
                    destination_root=destination,
                    template_preview=_template(),
                )
            assert exc_info.value.conflicts[0].target_path == target_dir / "XC-001 - Sample.mkv"

            plan = service.create_plan(
                mode="preview",
                media_items=[_media(video, sidecar)],
                destination_root=destination,
                template_preview=_template(filename="Other.mkv"),
                generated_artifacts=[
                    GeneratedArtifact(
                        relative_path="Other.nfo",
                        content_text="<movie />",
                        artifact_type="nfo",
                        allow_replace_existing=True,
                    )
                ],
            )
            assert plan.conflicts == ()
            replacement_step = next(step for step in plan.steps if step.generated_artifact)
            assert replacement_step.target_path == target_dir / "Other.nfo"
            assert replacement_step.allow_existing_generated_replacement is True
    finally:
        engine.dispose()


def test_planning_refuses_paths_outside_configured_storage_roots(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    outside = tmp_path / "outside"
    destination = outside / "organized"
    video = _write(incoming / "sample.mkv", b"video-bytes")
    sidecar = _write(incoming / "sample.srt", b"subtitle-bytes")
    destination.mkdir(parents=True)
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            service = OrganizerPlanService(
                session,
                StorageRootService(settings, session),
            )
            with pytest.raises(OperationPlanSafetyError, match="outside configured"):
                service.create_plan(
                    mode="copy",
                    media_items=[_media(video, sidecar)],
                    destination_root=destination,
                    template_preview=_template(),
                )

            outside_video = _write(outside / "sample.mkv", b"outside")
            with pytest.raises(OperationPlanSafetyError, match="outside configured"):
                service.create_plan(
                    mode="copy",
                    media_items=[_media(outside_video, sidecar)],
                    destination_root=root,
                    template_preview=_template(),
                )
    finally:
        engine.dispose()
