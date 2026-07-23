from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.db.models import OperationStep as OperationStepModel
from backend.app.schemas.actors import ActorOutputPlan
from backend.app.schemas.assets import MaterializedAsset, MaterializedAssetSet
from backend.app.schemas.media import MediaScanItem, MediaSidecarScanItem
from backend.app.schemas.operations import (
    GeneratedArtifact,
    OperationConflict,
    OperationFileSnapshot,
    OperationPlan,
    OperationSafetyWarning,
    OperationStep,
    OrganizationMode,
)
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.storage_roots import (
    StorageRootService,
    StorageRootValidationError,
)


class OperationPlanSafetyError(ValueError):
    pass


class OperationPlanConflictError(ValueError):
    def __init__(
        self,
        conflicts: tuple[OperationConflict, ...],
        *,
        plan: OperationPlan,
    ) -> None:
        super().__init__("Operation plan has destination conflicts")
        self.conflicts = conflicts
        self.plan = plan


class OrganizerPlanService:
    def __init__(self, session: Session, storage_roots: StorageRootService) -> None:
        self._session = session
        self._storage_roots = storage_roots

    def create_plan(
        self,
        *,
        mode: OrganizationMode,
        media_items: Sequence[MediaScanItem],
        destination_root: Path | str,
        template_preview: TemplatePreview,
        materialized_assets: MaterializedAssetSet | Sequence[MaterializedAsset] | None = None,
        generated_artifacts: Sequence[GeneratedArtifact] = (),
        actor_output_plans: Sequence[ActorOutputPlan] = (),
        job_id: int | None = None,
        plan_id: str | None = None,
    ) -> OperationPlan:
        plan = build_operation_plan(
            mode=mode,
            media_items=media_items,
            destination_root=destination_root,
            template_preview=template_preview,
            storage_roots=self._storage_roots,
            materialized_assets=materialized_assets,
            generated_artifacts=generated_artifacts,
            actor_output_plans=actor_output_plans,
            job_id=job_id,
            plan_id=plan_id,
        )
        if plan.conflicts:
            raise OperationPlanConflictError(plan.conflicts, plan=plan)

        row = OperationPlanModel(
            plan_id=plan.plan_id,
            job_id=job_id,
            version=plan.version,
            mode=plan.mode,
            status="planned",
            plan_json=plan.snapshot_json(),
            created_at=plan.created_at,
            updated_at=plan.created_at,
        )
        self._session.add(row)
        self._session.flush()
        for index, step in enumerate(plan.steps):
            self._session.add(
                OperationStepModel(
                    operation_plan_id=row.id,
                    step_id=step.step_id,
                    sequence=index,
                    operation=step.operation,
                    source_path=str(step.source_path) if step.source_path is not None else None,
                    target_path=str(step.target_path),
                    expected_size_bytes=step.expected_size_bytes,
                    sha256=step.sha256,
                    status="planned",
                    step_json=step.model_dump(mode="json"),
                    created_at=plan.created_at,
                    updated_at=plan.created_at,
                )
            )
        self._session.flush()
        return plan.model_copy(update={"database_id": row.id})


def build_operation_plan(
    *,
    mode: OrganizationMode,
    media_items: Sequence[MediaScanItem],
    destination_root: Path | str,
    template_preview: TemplatePreview,
    storage_roots: StorageRootService,
    materialized_assets: MaterializedAssetSet | Sequence[MaterializedAsset] | None = None,
    generated_artifacts: Sequence[GeneratedArtifact] = (),
    actor_output_plans: Sequence[ActorOutputPlan] = (),
    job_id: int | None = None,
    plan_id: str | None = None,
) -> OperationPlan:
    if mode not in {"preview", "in_place", "move", "copy", "hardlink", "symlink"}:
        raise OperationPlanSafetyError(f"Unsupported organization mode: {mode}")
    if not media_items:
        raise OperationPlanSafetyError("At least one media item is required")
    if template_preview.validation_errors:
        raise OperationPlanSafetyError(
            "Template preview has validation errors: "
            + ", ".join(template_preview.validation_errors)
        )
    if not template_preview.filename:
        raise OperationPlanSafetyError("Template preview did not produce a filename")

    destination_root_path = Path(destination_root)
    _validate_storage_path(storage_roots, destination_root_path, "destination root")
    folder_path = _safe_relative_path(template_preview.folder_path or "")
    target_directory = destination_root_path / folder_path
    _validate_storage_path(storage_roots, target_directory, "target directory")
    _validate_storage_path(storage_roots, target_directory.parent, "target parent")

    source_snapshot: list[OperationFileSnapshot] = []
    steps: list[OperationStep] = []
    seen_sidecars: set[Path] = set()
    target_filename = Path(template_preview.filename).name
    created_at = datetime.now(timezone.utc).replace(tzinfo=None)

    for index, item in enumerate(media_items, start=1):
        media_path = Path(item.path)
        _validate_storage_path(storage_roots, media_path, "source path")
        media_snapshot = _snapshot_file(media_path, kind="media")
        source_snapshot.append(media_snapshot)
        target_path = _target_media_path(
            target_directory,
            target_filename,
            media_path,
            item.multipart_index,
            force_part_suffix=len(media_items) > 1,
            sequence=index,
        )
        steps.append(
            _step(
                plan_id=plan_id,
                ordinal=len(steps) + 1,
                mode=mode,
                operation=_media_operation(mode),
                category="media",
                source_path=media_path,
                target_path=target_path,
                expected_size_bytes=item.size_bytes,
                mtime_ns=item.mtime_ns,
                sha256=media_snapshot.sha256,
                destructive=mode in {"move", "in_place"},
                storage_roots=storage_roots,
            )
        )
        for sidecar in item.sidecars:
            sidecar_path = Path(sidecar.path)
            if sidecar_path in seen_sidecars:
                continue
            seen_sidecars.add(sidecar_path)
            _validate_storage_path(storage_roots, sidecar_path, "sidecar source path")
            sidecar_snapshot = _snapshot_file(
                sidecar_path,
                kind=sidecar.kind,
                sidecar=True,
            )
            source_snapshot.append(sidecar_snapshot)
            sidecar_target = target_path.with_suffix(sidecar_path.suffix)
            steps.append(
                _step(
                    plan_id=plan_id,
                    ordinal=len(steps) + 1,
                    mode=mode,
                    operation=_media_operation(mode),
                    category="sidecar",
                    source_path=sidecar_path,
                    target_path=sidecar_target,
                    expected_size_bytes=sidecar_snapshot.expected_size_bytes,
                    mtime_ns=sidecar_snapshot.mtime_ns,
                    sha256=sidecar_snapshot.sha256,
                    sidecar=True,
                    destructive=mode in {"move", "in_place"},
                    storage_roots=storage_roots,
                    metadata={"kind": sidecar.kind},
                )
            )

    cache_paths: list[Path] = []
    for asset in _asset_list(materialized_assets):
        source_path = Path(asset.cache_path)
        cache_paths.append(source_path)
        steps.append(
            _step(
                plan_id=plan_id,
                ordinal=len(steps) + 1,
                mode=mode,
                operation=_asset_operation(mode),
                category="asset",
                source_path=source_path,
                target_path=target_directory / _safe_relative_path(asset.relative_path),
                expected_size_bytes=asset.size_bytes,
                sha256=asset.sha256,
                materialized_asset=True,
                storage_roots=storage_roots,
                metadata=redact_payload(
                    {
                        "kind": asset.kind,
                        "content_type": asset.content_type,
                        "actor_name": asset.actor_name,
                        "actor_source_id": asset.actor_source_id,
                    }
                ),
            )
        )

    for artifact in generated_artifacts:
        content = _generated_bytes(artifact)
        digest = artifact.sha256 or hashlib.sha256(content).hexdigest()
        expected_size = artifact.expected_size_bytes
        if expected_size is None:
            expected_size = len(content)
        steps.append(
            _step(
                plan_id=plan_id,
                ordinal=len(steps) + 1,
                mode=mode,
                operation="write_generated",
                category="generated_artifact",
                source_path=None,
                target_path=target_directory / _safe_relative_path(artifact.relative_path),
                expected_size_bytes=expected_size,
                sha256=digest,
                generated_artifact=True,
                allow_existing_generated_replacement=artifact.allow_replace_existing,
                storage_roots=storage_roots,
                metadata={
                    "artifact_type": artifact.artifact_type,
                    "content_text": artifact.content_text,
                },
            )
        )

    for actor_output in actor_output_plans:
        source_path = Path(actor_output.source_path)
        target_path = Path(actor_output.destination_path)
        cache_paths.append(source_path)
        steps.append(
            _step(
                plan_id=plan_id,
                ordinal=len(steps) + 1,
                mode=mode,
                operation=_actor_operation(mode, actor_output.operation),
                category="actor_output",
                source_path=source_path,
                target_path=target_path,
                expected_size_bytes=_existing_size(source_path),
                sha256=_existing_sha256(source_path),
                actor_output=True,
                storage_roots=storage_roots,
                metadata=redact_payload(
                    {
                        "actor_name": actor_output.actor_name,
                        "actor_source_id": actor_output.actor_source_id,
                        "relative_path": str(actor_output.relative_path),
                    }
                ),
            )
        )

    conflicts = _find_conflicts(steps)
    warnings = tuple(
        OperationSafetyWarning(code=warning, message=warning)
        for warning in template_preview.warnings
    )
    concrete_plan_id = plan_id or f"plan_{uuid.uuid4().hex}"
    return OperationPlan(
        plan_id=concrete_plan_id,
        version=1,
        job_id=job_id,
        mode=mode,
        destination_root=destination_root_path,
        target_directory=target_directory,
        source_snapshot=tuple(source_snapshot),
        materialized_asset_cache_paths=tuple(dict.fromkeys(cache_paths)),
        steps=tuple(
            _with_final_step_id(step, concrete_plan_id)
            for step in steps
        ),
        conflicts=tuple(conflicts),
        safety_warnings=warnings,
        created_at=created_at,
    )


def _step(
    *,
    plan_id: str | None,
    ordinal: int,
    mode: OrganizationMode,
    operation: str,
    category: str,
    source_path: Path | None,
    target_path: Path,
    storage_roots: StorageRootService,
    expected_size_bytes: int | None = None,
    mtime_ns: int | None = None,
    sha256: str | None = None,
    sidecar: bool = False,
    materialized_asset: bool = False,
    generated_artifact: bool = False,
    actor_output: bool = False,
    destructive: bool = False,
    allow_existing_generated_replacement: bool = False,
    metadata: dict[str, object] | None = None,
) -> OperationStep:
    effective_operation = "preview" if mode == "preview" else operation
    if source_path is not None:
        _validate_storage_path(storage_roots, source_path, "source path")
    _validate_storage_path(storage_roots, target_path, "target path")
    _validate_storage_path(storage_roots, target_path.parent, "target parent")
    _validate_storage_path(storage_roots, target_path.parent, "temp parent")
    step_plan_id = plan_id or "pending"
    return OperationStep(
        step_id=f"{step_plan_id}:{ordinal:04d}",
        operation=effective_operation,
        category=category,  # type: ignore[arg-type]
        source_path=source_path,
        target_path=target_path,
        temp_parent_path=target_path.parent,
        expected_size_bytes=expected_size_bytes,
        mtime_ns=mtime_ns,
        sha256=sha256,
        sidecar=sidecar,
        materialized_asset=materialized_asset,
        generated_artifact=generated_artifact,
        actor_output=actor_output,
        destructive=False if mode == "preview" else destructive,
        allow_existing_generated_replacement=allow_existing_generated_replacement,
        metadata=dict(metadata or {}),
    )


def _with_final_step_id(step: OperationStep, plan_id: str) -> OperationStep:
    if step.step_id.startswith(f"{plan_id}:"):
        return step
    _pending, ordinal = step.step_id.split(":", 1)
    return step.model_copy(update={"step_id": f"{plan_id}:{ordinal}"})


def _media_operation(mode: OrganizationMode) -> str:
    return {
        "preview": "preview",
        "in_place": "rename",
        "move": "move",
        "copy": "copy",
        "hardlink": "hardlink",
        "symlink": "symlink",
    }[mode]


def _asset_operation(mode: OrganizationMode) -> str:
    return {
        "preview": "preview",
        "in_place": "copy",
        "move": "copy",
        "copy": "copy",
        "hardlink": "hardlink",
        "symlink": "symlink",
    }[mode]


def _actor_operation(mode: OrganizationMode, requested: str) -> str:
    if mode == "preview":
        return "preview"
    if mode in {"hardlink", "symlink"}:
        return mode
    if requested in {"copy", "hardlink", "symlink"}:
        return requested
    return "copy"


def _target_media_path(
    target_directory: Path,
    template_filename: str,
    source_path: Path,
    multipart_index: int | None,
    *,
    force_part_suffix: bool,
    sequence: int,
) -> Path:
    template_path = Path(template_filename)
    suffix = source_path.suffix or template_path.suffix
    stem = template_path.stem
    if multipart_index is not None:
        stem = f"{stem} - part{multipart_index:02d}"
    elif force_part_suffix:
        stem = f"{stem} - part{sequence:02d}"
    return target_directory / f"{stem}{suffix}"


def _asset_list(
    materialized_assets: MaterializedAssetSet | Sequence[MaterializedAsset] | None,
) -> list[MaterializedAsset]:
    if materialized_assets is None:
        return []
    if isinstance(materialized_assets, MaterializedAssetSet):
        return list(materialized_assets.assets)
    return list(materialized_assets)


def _snapshot_file(path: Path, *, kind: str, sidecar: bool = False) -> OperationFileSnapshot:
    stat = path.stat()
    return OperationFileSnapshot(
        path=path,
        kind=kind,
        expected_size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=_hash_file(path),
        sidecar=sidecar,
    )


def _existing_size(path: Path) -> int | None:
    if not path.exists():
        return None
    return path.stat().st_size


def _existing_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return _hash_file(path)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generated_bytes(artifact: GeneratedArtifact) -> bytes:
    if artifact.content_text is None:
        return b""
    return artifact.content_text.encode("utf-8")


def _safe_relative_path(path: str | Path) -> Path:
    relative = Path(path)
    if str(path) in {"", "."}:
        return Path()
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise OperationPlanSafetyError("Relative output path escapes target directory")
    return relative


def _validate_storage_path(
    storage_roots: StorageRootService,
    path: Path,
    label: str,
) -> None:
    try:
        storage_roots.validate_inside_root(path)
    except StorageRootValidationError as exc:
        raise OperationPlanSafetyError(
            f"{label} is outside configured storage roots"
        ) from exc


def _find_conflicts(steps: Sequence[OperationStep]) -> list[OperationConflict]:
    conflicts: list[OperationConflict] = []
    planned_targets: dict[Path, OperationStep] = {}
    for step in steps:
        target = step.target_path
        previous = planned_targets.get(target)
        if previous is not None:
            conflicts.append(
                OperationConflict(
                    target_path=target,
                    source_path=step.source_path,
                    reason="duplicate_planned_target",
                )
            )
            continue
        planned_targets[target] = step
        if not target.exists():
            continue
        if _source_is_target(step.source_path, target):
            continue
        if step.generated_artifact and step.allow_existing_generated_replacement:
            continue
        conflicts.append(
            OperationConflict(
                target_path=target,
                source_path=step.source_path,
                reason="target_exists",
            )
        )
    return conflicts


def _source_is_target(source_path: Path | None, target_path: Path) -> bool:
    if source_path is None:
        return False
    try:
        return source_path.exists() and target_path.exists() and source_path.samefile(target_path)
    except OSError:
        return False
