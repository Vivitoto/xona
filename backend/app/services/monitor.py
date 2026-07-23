from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import Job, MonitorMediaState, WatchRule
from backend.app.services.scanner import VIDEO_EXTENSIONS, media_identity, scan_directory
from backend.app.services.stability import StabilityDetector, StabilitySnapshot
from backend.app.services.watch_rules import WatchRuleService, WatchRuleValidationError


class MonitorObserver(Protocol):
    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def join(self, timeout: float | None = None) -> None:
        ...


ObserverFactory = Callable[["MonitorService"], MonitorObserver]


class MonitorService:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: sessionmaker[Session],
        *,
        observer_factory: ObserverFactory | None = None,
    ) -> None:
        self._settings = settings
        self._sessionmaker = sessionmaker
        self._observer_factory = observer_factory
        self._observer: MonitorObserver | None = None
        self.active_rule_ids: set[str] = set()
        self.polling_rule_ids: set[str] = set()
        self.realtime_available = False
        self.started = False

    def start(self) -> None:
        self.reload_rules()
        self.started = True
        realtime_requested = self._has_realtime_rules()
        if not realtime_requested:
            self.realtime_available = False
            self.polling_rule_ids = set(self.active_rule_ids)
            return
        try:
            observer = self._build_observer()
            if observer is None:
                raise RuntimeError("watchdog unavailable")
            observer.start()
        except Exception:
            self._observer = None
            self.realtime_available = False
            self.polling_rule_ids = set(self.active_rule_ids)
            return
        self._observer = observer
        self.realtime_available = True
        self._refresh_polling_rule_ids()

    def stop(self) -> None:
        observer = self._observer
        self._observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout=2.0)
        self.started = False

    def reload_rules(self) -> None:
        with self._sessionmaker() as session:
            rules = [rule for rule in WatchRuleService(self._settings, session).list_rules() if rule.enabled]
            self.active_rule_ids = {rule.rule_id for rule in rules}
            self._refresh_polling_rule_ids(rules=rules)

    def handle_event(self, path: Path | str, *, rule_id: str | None = None) -> list[Job]:
        media_path = Path(path)
        with self._sessionmaker() as session:
            service = WatchRuleService(self._settings, session)
            rules = self._candidate_rules(service, media_path, rule_id=rule_id)
            jobs: list[Job] = []
            for rule in rules:
                job = self._process_path(service, rule, media_path)
                if job is not None:
                    jobs.append(job)
            session.commit()
            for job in jobs:
                session.refresh(job)
            return jobs

    def scan_rule_once(self, rule_id: str) -> list[Job]:
        with self._sessionmaker() as session:
            service = WatchRuleService(self._settings, session)
            rule = service.get_rule(rule_id)
            jobs: list[Job] = []
            for item in scan_directory(
                rule.source_directory,
                recursive=rule.recursive,
                storage_roots=service.storage_roots,
            ):
                if not service.path_allowed(rule, item.path):
                    continue
                job = self._process_path(service, rule, item.path)
                if job is not None:
                    jobs.append(job)
            session.commit()
            for job in jobs:
                session.refresh(job)
            return jobs

    def _process_path(
        self,
        service: WatchRuleService,
        rule: WatchRule,
        path: Path,
    ) -> Job | None:
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            return None
        if not path.exists() or not path.is_file():
            return None
        if not _is_relative_to(path, Path(rule.source_directory)):
            return None
        if not service.path_allowed(rule, path):
            return None
        stat = path.stat()
        identity = media_identity(path, stat_result=stat)
        previous_state = service.get_state(rule.rule_id, identity)
        previous = _snapshot_from_state(previous_state)
        result = StabilityDetector(
            minimum_age_seconds=rule.stability_seconds,
            required_stable_checks=rule.stable_check_count,
        ).evaluate(
            path,
            previous=previous,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )
        service.record_seen(
            rule_id=rule.rule_id,
            media_identity=identity,
            last_seen_path=path,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            stable_count=result.snapshot.stable_count,
        )
        if not result.stable:
            return None
        return service.enqueue_once(
            rule,
            media_identity=identity,
            last_seen_path=path,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            stable_count=result.snapshot.stable_count,
        )

    def _candidate_rules(
        self,
        service: WatchRuleService,
        path: Path,
        *,
        rule_id: str | None,
    ) -> list[WatchRule]:
        if rule_id is not None:
            try:
                rule = service.get_rule(rule_id)
            except WatchRuleValidationError:
                return []
            return [rule]
        return [
            rule
            for rule in service.list_rules()
            if rule.enabled and _is_relative_to(path, Path(rule.source_directory))
        ]

    def _has_realtime_rules(self) -> bool:
        with self._sessionmaker() as session:
            return any(
                rule.enabled and rule.realtime
                for rule in WatchRuleService(self._settings, session).list_rules()
            )

    def _build_observer(self) -> MonitorObserver | None:
        if self._observer_factory is not None:
            return self._observer_factory(self)
        return None

    def _refresh_polling_rule_ids(self, *, rules: list[WatchRule] | None = None) -> None:
        if rules is None:
            with self._sessionmaker() as session:
                rules = [
                    rule
                    for rule in WatchRuleService(self._settings, session).list_rules()
                    if rule.enabled
                ]
        if not self.realtime_available:
            self.polling_rule_ids = {rule.rule_id for rule in rules}
        else:
            self.polling_rule_ids = {
                rule.rule_id for rule in rules if not rule.realtime
            }


def _snapshot_from_state(state: MonitorMediaState | None) -> StabilitySnapshot | None:
    if state is None or state.size_bytes is None or state.mtime_ns is None:
        return None
    return StabilitySnapshot(
        size_bytes=state.size_bytes,
        mtime_ns=state.mtime_ns,
        stable_count=state.stable_count,
    )


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base.resolve(strict=False))
    except ValueError:
        return False
    return True
