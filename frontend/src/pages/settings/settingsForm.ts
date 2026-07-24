import type { AppSettings, AppSettingsUpdate } from "../../api/types";
import { REDACTED_PLACEHOLDER } from "../../api/types";
import { isRedactedPlaceholder } from "../../utils/redaction";

export const emptySettings: AppSettings = {
  storage: {
    roots: [],
    env_roots: [],
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

export const namingTemplateVariables = new Set([
  "number",
  "title",
  "original_title",
  "studio",
  "series",
  "year",
  "release_date",
  "actors",
  "first_actor",
  "source_filename",
  "xchina_id",
]);

export interface SettingsValidationResult {
  errors: string[];
  warnings: string[];
  changes: string[];
}

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

export function validateSettings(
  settings: AppSettings,
  baseline: AppSettings | null = null,
): SettingsValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const changes: string[] = [];

  if (!cleanOptional(settings.xchina.base_url)) {
    errors.push("XChina 基础 URL 不能为空。");
  }
  if (settings.xchina.base_url && !looksLikeHttpUrl(settings.xchina.base_url)) {
    warnings.push("XChina 基础 URL 看起来不是 http/https 地址。");
  }
  if (settings.xchina.flaresolverr_url && !looksLikeHttpUrl(settings.xchina.flaresolverr_url)) {
    warnings.push("FlareSolverr 端点看起来不是 http/https 地址。");
  }
  if (settings.xchina.proxy_url && !isRedactedPlaceholder(settings.xchina.proxy_url) && !looksLikeHttpUrl(settings.xchina.proxy_url)) {
    warnings.push("代理 URL 看起来不是 http/https 地址。");
  }

  const userRoots = uniqueClean(settings.storage.roots);
  const duplicateRoots = duplicates(settings.storage.roots.map((root) => root.trim()).filter(Boolean));
  if (duplicateRoots.length) {
    warnings.push(`用户媒体目录存在重复项：${duplicateRoots.join("、")}`);
  }
  const envRootCollisions = userRoots.filter((root) => settings.storage.env_roots.includes(root));
  if (envRootCollisions.length) {
    warnings.push(`这些媒体目录已由容器挂载自动提供，保存时会忽略重复项：${envRootCollisions.join("、")}`);
  }
  if (!userRoots.length && !settings.storage.env_roots.length) {
    warnings.push("尚未配置媒体目录；手动整理和自动监控需要至少一个媒体根目录。请选择或输入一个目录。");
  }

  if (settings.emby.enabled && !cleanOptional(settings.emby.server_url)) {
    errors.push("启用 Emby 通知时必须填写 Emby 服务器 URL。");
  }
  if (settings.emby.server_url && !looksLikeHttpUrl(settings.emby.server_url)) {
    warnings.push("Emby 服务器 URL 看起来不是 http/https 地址。");
  }
  for (const [index, mapping] of settings.emby.path_mappings.entries()) {
    const hasContainer = Boolean(mapping.container_root.trim());
    const hasEmby = Boolean(mapping.emby_root.trim());
    if (hasContainer !== hasEmby) {
      errors.push(`Emby 路径映射 #${index + 1} 需要同时填写容器根目录和 Emby 可见根目录。`);
    }
  }

  const folderTemplates = settings.naming.folder_templates.map((template) => template.trim()).filter(Boolean);
  const filenameTemplate = settings.naming.filename_template.trim();
  if (!filenameTemplate) {
    errors.push("文件名模板不能为空。");
  }
  if (!folderTemplates.length) {
    errors.push("至少需要一个文件夹模板。");
  }
  const unknownVariables = Array.from(
    new Set([
      ...folderTemplates.flatMap(extractUnknownTemplateVariables),
      ...extractUnknownTemplateVariables(filenameTemplate),
    ]),
  );
  if (unknownVariables.length) {
    errors.push(`命名模板包含未知变量：${unknownVariables.map((name) => `{${name}}`).join("、")}`);
  }
  if (!filenameTemplate.includes("{title}") && !filenameTemplate.includes("{number}") && !filenameTemplate.includes("{xchina_id}")) {
    warnings.push("文件名模板没有包含标题、番号或 XChina ID，可能难以辨认。建议至少包含 {title}、{number} 或 {xchina_id}。 ");
  }

  if (settings.confidence_safety.confidence_threshold < 0 || settings.confidence_safety.confidence_threshold > 100) {
    errors.push("置信度阈值必须在 0 到 100 之间。");
  }
  if (settings.metadata_assets.max_asset_bytes <= 0) {
    errors.push("最大资源大小必须大于 0。 ");
  }

  if (baseline) {
    changes.push(...summarizeChanges(settings, baseline));
  }

  return { errors, warnings, changes };
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
    throw new Error("需要输入 JSON 对象");
  }
  return parsed as Record<string, unknown>;
}

function summarizeChanges(settings: AppSettings, baseline: AppSettings): string[] {
  const changes: string[] = [];
  if (!sameList(settings.storage.roots, baseline.storage.roots)) {
    changes.push("用户媒体目录将更新");
  }
  if (settings.xchina.base_url !== baseline.xchina.base_url) {
    changes.push("XChina 基础 URL 将更新");
  }
  if (settings.xchina.flaresolverr_url !== baseline.xchina.flaresolverr_url) {
    changes.push("FlareSolverr 端点将更新");
  }
  if (settings.xchina.proxy_url !== baseline.xchina.proxy_url) {
    changes.push(isRedactedPlaceholder(settings.xchina.proxy_url) ? "代理凭据保持不变" : "代理 URL 将更新");
  }
  if (settings.emby.enabled !== baseline.emby.enabled) {
    changes.push(settings.emby.enabled ? "将启用 Emby 通知" : "将关闭 Emby 通知");
  }
  if (settings.emby.server_url !== baseline.emby.server_url) {
    changes.push("Emby 服务器 URL 将更新");
  }
  if (settings.emby.api_key !== baseline.emby.api_key) {
    changes.push(isRedactedPlaceholder(settings.emby.api_key) ? "Emby API key 保持不变" : "Emby API key 将更新");
  }
  if (JSON.stringify(settings.emby.path_mappings) !== JSON.stringify(baseline.emby.path_mappings)) {
    changes.push("Emby 路径映射将更新");
  }
  if (!sameList(settings.naming.folder_templates, baseline.naming.folder_templates) || settings.naming.filename_template !== baseline.naming.filename_template) {
    changes.push("命名模板将更新");
  }
  if (JSON.stringify(settings.metadata_assets) !== JSON.stringify(baseline.metadata_assets)) {
    changes.push("元数据/资源策略将更新");
  }
  if (JSON.stringify(settings.confidence_safety) !== JSON.stringify(baseline.confidence_safety)) {
    changes.push("置信度/安全策略将更新");
  }
  if (JSON.stringify(settings.auth) !== JSON.stringify(baseline.auth)) {
    changes.push("认证设置将更新");
  }
  return changes;
}

function extractUnknownTemplateVariables(template: string): string[] {
  const variables = template.matchAll(/\{([^{}]+)\}/g);
  return Array.from(variables)
    .map((match) => match[1].trim())
    .filter((name) => !namingTemplateVariables.has(name));
}

function uniqueClean(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function duplicates(values: string[]): string[] {
  const seen = new Set<string>();
  const duplicated = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) {
      duplicated.add(value);
    }
    seen.add(value);
  }
  return Array.from(duplicated);
}

function sameList(a: string[], b: string[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function looksLikeHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
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
