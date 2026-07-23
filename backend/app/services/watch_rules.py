from __future__ import annotations

import fnmatch
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import Job, MonitorMediaState, WatchRule
from backend.app.schemas.watch_rules import WatchRuleCreate, WatchRuleUpdate
from backend.app.services.jobs import ACTIVE_STATES, JobService
from backend.app.services.scanner import scan_directory
from backend.app.services.storage_roots import (
    StorageRootService,
    StorageRootValidationError,
)


class WatchRuleValidationError(ValueError):
    pass


class WatchRuleService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session
        self._storage_roots = StorageRootService(settings, session)

    def list_rules(self) -> list[WatchRule]:
        return list(self._session.scalars(select(WatchRule).order_by(WatchRule.id)))

    def get_rule(self, rule_id: str) -> WatchRule:
        rule = self._session.scalar(
            select(WatchRule).where(WatchRule.rule_id == rule_id)
        )
        if rule is None:
            raise WatchRuleValidationError("Watch rule not found")
        return rule

    def create_rule(self, payload: WatchRuleCreate) -> WatchRule:
        values = payload.model_dump()
        source = Path(values["source_directory"])
        destination = Path(values["destination_directory"])
        excluded = self._validated_excluded_prefixes(
            source,
            destination,
            values["excluded_destination_prefixes"],
        )
        self._validate_source_destination(source, destination)
        now_rule = WatchRule(
            rule_id=f"rule_{uuid.uuid4().hex}",
            source_directory=str(source),
            destination_directory=str(destination),
            recursive=values["recursive"],
            realtime=values["realtime"],
            polling_interval_seconds=values["polling_interval_seconds"],
            stability_seconds=values["stability_seconds"],
            stable_check_count=values["stable_check_count"],
            organization_mode=values["organization_mode"],
            folder_templates=list(values["folder_templates"]),
            filename_template=values["filename_template"],
            asset_policy=values["asset_policy"],
            emby_options=dict(values["emby_options"]),
            metadata_options=dict(values["metadata_options"]),
            include_patterns=list(values["include_patterns"]),
            exclude_patterns=list(values["exclude_patterns"]),
            excluded_destination_prefixes=[str(path) for path in excluded],
            confidence_threshold=values["confidence_threshold"],
            enabled=values["enabled"],
        )
        self._session.add(now_rule)
        self._session.flush()
        return now_rule

    def update_rule(self, rule_id: str, payload: WatchRuleUpdate) -> WatchRule:
        rule = self.get_rule(rule_id)
        updates = payload.model_dump(exclude_unset=True)
        source = Path(updates.get("source_directory") or rule.source_directory)
        destination = Path(updates.get("destination_directory") or rule.destination_directory)
        excluded_input = updates.get(
            "excluded_destination_prefixes",
            [Path(path) for path in rule.excluded_destination_prefixes],
        )
        excluded = self._validated_excluded_prefixes(source, destination, excluded_input)
        self._validate_source_destination(source, destination)

        for field, value in updates.items():
            if field in {"source_directory", "destination_directory"}:
                setattr(rule, field, str(value))
            elif field == "excluded_destination_prefixes":
                continue
            else:
                setattr(rule, field, value)
        rule.source_directory = str(source)
        rule.destination_directory = str(destination)
        rule.excluded_destination_prefixes = [str(path) for path in excluded]
        self._session.flush()
        return rule

    def delete_rule(self, rule_id: str) -> None:
        rule = self.get_rule(rule_id)
        self._session.delete(rule)
        self._session.flush()

    def enqueue_once(
        self,
        rule: WatchRule,
        *,
        media_identity: str,
        last_seen_path: Path | str,
        size_bytes: int,
        mtime_ns: int,
        stable_count: int,
    ) -> Job:
        existing = self._active_job(rule.rule_id, media_identity)
        state = self._upsert_state(
            rule_id=rule.rule_id,
            media_identity=media_identity,
            last_seen_path=last_seen_path,
            size_bytes=size_bytes,
            mtime_ns=mtime_ns,
            stable_count=stable_count,
        )
        if existing is not None:
            state.last_enqueued_job_id = existing.id
            self._session.flush()
            return existing
        try:
            job = JobService(self._session).create_job(
                media_identity=media_identity,
                rule_id=rule.rule_id,
                manual=False,
                state="waiting_stable",
                payload={
                    "rule_id": rule.rule_id,
                    "last_seen_path": str(last_seen_path),
                    "size_bytes": size_bytes,
                    "mtime_ns": mtime_ns,
                },
            )
            state.last_enqueued_job_id = job.id
            self._session.flush()
            return job
        except IntegrityError:
            self._session.rollback()
            existing_after_race = self._active_job(rule.rule_id, media_identity)
            if existing_after_race is None:
                raise
            return existing_after_race

    def mark_terminal(
        self,
        rule_id: str,
        media_identity: str,
        *,
        terminal_state: str,
    ) -> None:
        state = self._state(rule_id, media_identity)
        if state is None:
            return
        state.terminal_state = terminal_state
        self._session.flush()

    def scan_now(self, rule_id: str) -> list[Job]:
        rule = self.get_rule(rule_id)
        jobs: list[Job] = []
        items = scan_directory(
            rule.source_directory,
            recursive=rule.recursive,
            storage_roots=self._storage_roots,
        )
        for item in items:
            if not self.path_allowed(rule, item.path):
                continue
            jobs.append(
                self.enqueue_once(
                    rule,
                    media_identity=item.identity,
                    last_seen_path=item.path,
                    size_bytes=item.size_bytes,
                    mtime_ns=item.mtime_ns,
                    stable_count=0,
                )
            )
        return jobs

    @property
    def storage_roots(self) -> StorageRootService:
        return self._storage_roots

    def get_state(
        self,
        rule_id: str,
        media_identity: str,
    ) -> MonitorMediaState | None:
        return self._state(rule_id, media_identity)

    def record_seen(
        self,
        *,
        rule_id: str,
        media_identity: str,
        last_seen_path: Path | str,
        size_bytes: int,
        mtime_ns: int,
        stable_count: int,
    ) -> MonitorMediaState:
        return self._upsert_state(
            rule_id=rule_id,
            media_identity=media_identity,
            last_seen_path=last_seen_path,
            size_bytes=size_bytes,
            mtime_ns=mtime_ns,
            stable_count=stable_count,
        )

    def path_allowed(self, rule: WatchRule, path: Path | str) -> bool:
        media_path = Path(path)
        for prefix in rule.excluded_destination_prefixes:
            if _is_relative_to(media_path, Path(prefix)):
                return False
        name = media_path.name
        if rule.include_patterns and not any(
            fnmatch.fnmatch(name, pattern) for pattern in rule.include_patterns
        ):
            return False
        if any(fnmatch.fnmatch(name, pattern) for pattern in rule.exclude_patterns):
            return False
        return True

    def _validated_excluded_prefixes(
        self,
        source: Path,
        destination: Path,
        configured: list[Path],
    ) -> list[Path]:
        excluded = [Path(path) for path in configured]
        if self._destination_inside_source(destination, source) and destination not in excluded:
            excluded.append(destination)
        return excluded

    def _validate_source_destination(self, source: Path, destination: Path) -> None:
        try:
            self._storage_roots.validate_inside_root(source)
            self._storage_roots.validate_inside_root(destination)
        except StorageRootValidationError as exc:
            raise WatchRuleValidationError("source or destination outside storage roots") from exc
        if not source.is_dir():
            raise WatchRuleValidationError("source directory is not readable")
        if not destination.is_dir():
            raise WatchRuleValidationError("destination directory is not writable")
        if not source.exists() or not _can_read(source):
            raise WatchRuleValidationError("source directory is not readable")
        if not _can_write(destination):
            raise WatchRuleValidationError("destination directory is not writable")

    def _destination_inside_source(self, destination: Path, source: Path) -> bool:
        try:
            return self._storage_roots.is_destination_inside_watch_source(
                destination,
                [source],
            )
        except Exception:
            return False

    def _active_job(self, rule_id: str, media_identity: str) -> Job | None:
        return self._session.scalar(
            select(Job)
            .where(
                Job.manual.is_(False),
                Job.rule_id == rule_id,
                Job.media_identity == media_identity,
                Job.state.in_(ACTIVE_STATES),
            )
            .order_by(Job.id)
        )

    def _upsert_state(
        self,
        *,
        rule_id: str,
        media_identity: str,
        last_seen_path: Path | str,
        size_bytes: int,
        mtime_ns: int,
        stable_count: int,
    ) -> MonitorMediaState:
        state = self._state(rule_id, media_identity)
        if state is None:
            state = MonitorMediaState(rule_id=rule_id, media_identity=media_identity)
            self._session.add(state)
            self._session.flush()
        state.last_seen_path = str(last_seen_path)
        state.size_bytes = size_bytes
        state.mtime_ns = mtime_ns
        state.stable_count = stable_count
        self._session.flush()
        return state

    def _state(self, rule_id: str, media_identity: str) -> MonitorMediaState | None:
        return self._session.scalar(
            select(MonitorMediaState).where(
                MonitorMediaState.rule_id == rule_id,
                MonitorMediaState.media_identity == media_identity,
            )
        )


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base.resolve(strict=False))
    except ValueError:
        return False
    return True


def _can_read(path: Path) -> bool:
    return path.exists() and path.is_dir()


def _can_write(path: Path) -> bool:
    probe = path / f".xona-write-test-{uuid.uuid4().hex}"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True
