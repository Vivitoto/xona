from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.watch_rules import WatchRuleCreate, WatchRuleUpdate
from backend.app.services.settings_store import SettingsStore
from backend.app.services.watch_rules import WatchRuleService, WatchRuleValidationError


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def test_watch_rule_stores_full_configuration_and_loop_exclusions(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = source / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            service = WatchRuleService(settings, session)
            rule = service.create_rule(
                WatchRuleCreate(
                    source_directory=source,
                    destination_directory=destination,
                    recursive=True,
                    realtime=False,
                    polling_interval_seconds=45,
                    stability_seconds=120,
                    stable_check_count=3,
                    organization_mode="hardlink",
                    folder_templates=["{studio}", "{series}"],
                    filename_template="{number} - {title}.mkv",
                    asset_policy="lenient",
                    emby_options={"enabled": True, "library_id": "lib-1"},
                    include_patterns=["*.mkv", "*.mp4"],
                    exclude_patterns=["sample*"],
                    confidence_threshold=97,
                )
            )
            session.commit()

            loaded = service.get_rule(rule.rule_id)
            assert loaded.rule_id == rule.rule_id
            assert loaded.source_directory == str(source)
            assert loaded.destination_directory == str(destination)
            assert loaded.recursive is True
            assert loaded.realtime is False
            assert loaded.polling_interval_seconds == 45
            assert loaded.stability_seconds == 120
            assert loaded.stable_check_count == 3
            assert loaded.organization_mode == "hardlink"
            assert loaded.folder_templates == ["{studio}", "{series}"]
            assert loaded.filename_template == "{number} - {title}.mkv"
            assert loaded.asset_policy == "lenient"
            assert loaded.emby_options["library_id"] == "lib-1"
            assert loaded.include_patterns == ["*.mkv", "*.mp4"]
            assert loaded.exclude_patterns == ["sample*"]
            assert loaded.confidence_threshold == 97
            assert str(destination) in loaded.excluded_destination_prefixes

            updated = service.update_rule(
                rule.rule_id,
                WatchRuleUpdate(enabled=False, organization_mode="copy"),
            )
            assert updated.enabled is False
            assert updated.organization_mode == "copy"
    finally:
        engine.dispose()


def test_watch_rule_validation_checks_readable_source_and_writable_destination(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = root / "missing"
    destination = root / "organized"
    root.mkdir(parents=True)
    destination.mkdir()
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            service = WatchRuleService(settings, session)
            with pytest.raises(WatchRuleValidationError, match="source"):
                service.create_rule(
                    WatchRuleCreate(
                        source_directory=source,
                        destination_directory=destination,
                    )
                )
    finally:
        engine.dispose()


def test_watch_rule_create_uses_organization_defaults_for_empty_fields(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    settings, engine, sessionmaker = _database(tmp_path, root)
    try:
        with sessionmaker() as session:
            SettingsStore(session).update_app_settings(
                {
                    "organization_defaults": {
                        "destination_directory": str(destination),
                        "organization_mode": "move",
                        "folder_templates": ["{studio}", "{xchina_id}"],
                        "filename_template": "{xchina_id} - {title}",
                        "asset_policy": "strict",
                        "include_source_snapshot": True,
                    }
                }
            )
            service = WatchRuleService(settings, session)
            rule = service.create_rule(
                WatchRuleCreate(
                    source_directory=source,
                    destination_directory=None,
                    folder_templates=[],
                    filename_template=None,
                    asset_policy=None,
                )
            )

            assert rule.destination_directory == str(destination)
            assert rule.organization_mode == "move"
            assert rule.folder_templates == ["{studio}", "{xchina_id}"]
            assert rule.filename_template == "{xchina_id} - {title}"
            assert rule.asset_policy == "strict"
    finally:
        engine.dispose()
