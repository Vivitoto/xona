import type { AppSettings, AppSettingsUpdate } from "../../api/types";
import { REDACTED_PLACEHOLDER } from "../../api/types";
import { isRedactedPlaceholder } from "../../utils/redaction";

export const emptySettings: AppSettings = {
  storage: {
    roots: [],
  },
  xchina: {
    base_url: "https://www.xchina.co",
    flaresolverr_url: null,
    proxy_url: null,
    cache_dir: null,
  },
  emby: {
    enabled: false,
    server_url: null,
    api_key: null,
    path_mappings: [],
    upload_actor_portraits: true,
  },
  naming: {
    folder_templates: ["{studio}", "{title}"],
    filename_template: "{title}",
  },
  metadata_assets: {
    write_nfo: true,
    include_source_snapshot: false,
    asset_policy: "lenient",
    max_asset_bytes: 10485760,
  },
  confidence_safety: {
    confidence_threshold: 92,
    refuse_destination_collisions: true,
    refuse_unresolved_multipart: true,
    cache_dir: null,
  },
  auth: {
    enabled: false,
    username: null,
  },
};

export function normalizeSettings(input: Partial<AppSettings>): AppSettings {
  return {
    storage: { ...emptySettings.storage, ...input.storage },
    xchina: { ...emptySettings.xchina, ...input.xchina },
    emby: { ...emptySettings.emby, ...input.emby },
    naming: { ...emptySettings.naming, ...input.naming },
    metadata_assets: {
      ...emptySettings.metadata_assets,
      ...input.metadata_assets,
    },
    confidence_safety: {
      ...emptySettings.confidence_safety,
      ...input.confidence_safety,
    },
    auth: { ...emptySettings.auth, ...input.auth },
  };
}

export function buildSettingsPayload(settings: AppSettings): AppSettingsUpdate {
  const proxyUrl = cleanOptionalSecret(settings.xchina.proxy_url);
  const apiKey = cleanOptionalSecret(settings.emby.api_key);

  const payload: AppSettingsUpdate = {
    storage: {
      roots: settings.storage.roots.filter(Boolean),
    },
    xchina: {
      base_url: cleanOptional(settings.xchina.base_url) ?? emptySettings.xchina.base_url,
      flaresolverr_url: cleanOptional(settings.xchina.flaresolverr_url),
      proxy_url: proxyUrl,
      cache_dir: cleanOptional(settings.xchina.cache_dir),
    },
    emby: {
      enabled: settings.emby.enabled,
      server_url: cleanOptional(settings.emby.server_url),
      api_key: apiKey,
      path_mappings: settings.emby.path_mappings.filter(
        (mapping) => mapping.container_root.trim() || mapping.emby_root.trim(),
      ),
      upload_actor_portraits: settings.emby.upload_actor_portraits,
    },
    naming: {
      folder_templates: settings.naming.folder_templates.filter(Boolean),
      filename_template:
        cleanOptional(settings.naming.filename_template) ??
        emptySettings.naming.filename_template,
    },
    metadata_assets: {
      ...settings.metadata_assets,
    },
    confidence_safety: {
      ...settings.confidence_safety,
      cache_dir: cleanOptional(settings.confidence_safety.cache_dir),
    },
    auth: {
      enabled: settings.auth.enabled,
      username: cleanOptional(settings.auth.username),
    },
  };

  if (apiKey === undefined) {
    delete payload.emby?.api_key;
  }
  if (proxyUrl === undefined) {
    delete payload.xchina?.proxy_url;
  }
  return payload;
}

export function linesToList(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function listToLines(value: string[]): string {
  return value.join("\n");
}

export function parseJsonObject(value: string): Record<string, unknown> {
  if (!value.trim()) {
    return {};
  }
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Expected a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function cleanOptional(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? "";
  return trimmed ? trimmed : null;
}

function cleanOptionalSecret(value: string | null | undefined): string | null | undefined {
  if (isRedactedPlaceholder(value)) {
    return undefined;
  }
  if (value === REDACTED_PLACEHOLDER) {
    return undefined;
  }
  return cleanOptional(value);
}
