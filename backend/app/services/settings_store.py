from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.redaction import REDACTED, redact_payload
from backend.app.db.models import Setting
from backend.app.schemas.settings import AppSettingsRead


APP_SETTINGS_KEY = "app_settings"
REDACTED_PLACEHOLDERS = {REDACTED, "********", "••••••••"}
SECRET_FIELDS = {"api_key", "password", "secret", "token"}


class SettingsUpdateError(ValueError):
    pass


class SettingsStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str, default: Any = None) -> Any:
        setting = self._session.get(Setting, key)
        if setting is None:
            return default
        return setting.value

    def get_public(self, key: str, default: Any = None) -> Any:
        setting = self._session.get(Setting, key)
        if setting is None:
            return default
        return redact_payload(setting.value)

    def set(self, key: str, value: Mapping[str, Any], *, secret: bool = False) -> Setting:
        setting = self._session.get(Setting, key)
        if setting is None:
            setting = Setting(key=key, value=dict(value), secret=secret)
            self._session.add(setting)
        else:
            setting.value = dict(value)
            setting.secret = secret
        return setting

    def get_app_settings(self, *, include_secrets: bool = False) -> dict[str, Any]:
        stored = _normalize_app_settings(self.get(APP_SETTINGS_KEY, {}))
        merged = _deep_merge(_default_app_settings(), stored)
        if include_secrets:
            return merged
        return redact_payload(merged)

    def update_app_settings(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        cleaned_patch = _normalize_app_settings(_plain_mapping(patch))
        _reject_redacted_placeholders(cleaned_patch)
        current = self.get_app_settings(include_secrets=True)
        merged = _deep_merge(current, cleaned_patch)
        self.set(APP_SETTINGS_KEY, merged, secret=False)
        self._session.flush()
        return redact_payload(merged)

    def organization_defaults(self) -> dict[str, Any]:
        settings = self.get_app_settings(include_secrets=True)
        defaults = settings.get("organization_defaults")
        return dict(defaults) if isinstance(defaults, dict) else {}

    def emby_settings(self) -> dict[str, Any]:
        settings = self.get_app_settings(include_secrets=True)
        emby = settings.get("emby")
        return dict(emby) if isinstance(emby, dict) else {}

    def xchina_settings(self) -> dict[str, Any]:
        settings = self.get_app_settings(include_secrets=True)
        xchina = settings.get("xchina")
        return dict(xchina) if isinstance(xchina, dict) else {}


def _default_app_settings() -> dict[str, Any]:
    return AppSettingsRead().model_dump(mode="json")


def _normalize_app_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    normalized = _plain_mapping(value)
    legacy_defaults = normalized.pop("manual_defaults", None)
    if "organization_defaults" not in normalized and isinstance(legacy_defaults, Mapping):
        normalized["organization_defaults"] = _plain_mapping(legacy_defaults)
    organization_defaults = normalized.get("organization_defaults")
    if isinstance(organization_defaults, Mapping):
        organization_defaults = _plain_mapping(organization_defaults)
        if organization_defaults.get("organization_mode") == "preview":
            organization_defaults["organization_mode"] = "copy"
        normalized["organization_defaults"] = organization_defaults
    return normalized


def _deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in patch.items():
        if (
            isinstance(value, Mapping)
            and isinstance(result.get(key), Mapping)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _reject_redacted_placeholders(value: Any, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_redacted_placeholders(item, path=(*path, str(key)))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_redacted_placeholders(item, path=(*path, str(index)))
        return
    if not isinstance(value, str):
        return
    if value not in REDACTED_PLACEHOLDERS:
        return
    field_name = path[-1] if path else ""
    if field_name in SECRET_FIELDS or any(fragment in field_name for fragment in SECRET_FIELDS):
        raise SettingsUpdateError("Redacted secret placeholder values are not accepted")


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    plain: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            plain[str(key)] = _plain_mapping(item)
        elif isinstance(item, list):
            plain[str(key)] = [
                _plain_mapping(child) if isinstance(child, Mapping) else child
                for child in item
            ]
        else:
            plain[str(key)] = item
    return plain
