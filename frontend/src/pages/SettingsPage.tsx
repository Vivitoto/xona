import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../api/client";
import type { AppSettings } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { Tabs, type TabItem } from "../components/Tabs";
import { AuthSettings } from "./settings/AuthSettings";
import { ConfidenceSafetySettings } from "./settings/ConfidenceSafetySettings";
import { EmbySettings } from "./settings/EmbySettings";
import { MetadataAssetSettings } from "./settings/MetadataAssetSettings";
import { NamingSettings } from "./settings/NamingSettings";
import { StorageSettings } from "./settings/StorageSettings";
import { XChinaSettings } from "./settings/XChinaSettings";
import {
  buildSettingsPayload,
  emptySettings,
  normalizeSettings,
  validateSettings,
} from "./settings/settingsForm";

type SettingsTab =
  | "xchina"
  | "emby"
  | "storage"
  | "naming"
  | "metadata"
  | "confidence"
  | "auth";

const settingsTabs: readonly TabItem<SettingsTab>[] = [
  { id: "xchina", label: "XChina" },
  { id: "emby", label: "Emby" },
  { id: "storage", label: "媒体目录" },
  { id: "naming", label: "命名模板" },
  { id: "metadata", label: "元数据/资源" },
  { id: "confidence", label: "置信度/安全" },
  { id: "auth", label: "认证" },
];

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(emptySettings);
  const [baselineSettings, setBaselineSettings] = useState<AppSettings | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>("xchina");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    apiFetch<AppSettings>("/api/settings")
      .then((payload) => {
        if (active) {
          const normalized = normalizeSettings(payload);
          setSettings(normalized);
          setBaselineSettings(normalized);
        }
      })
      .catch((exc) => {
        if (active) {
          setError(exc instanceof Error ? exc.message : "无法加载设置");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const validation = useMemo(
    () => validateSettings(settings, baselineSettings),
    [settings, baselineSettings],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("");
    setError("");

    if (validation.errors.length) {
      setError("请先修正保存前检查中的错误，再保存设置。");
      return;
    }

    try {
      const updated = await apiFetch<AppSettings>("/api/settings", {
        method: "PUT",
        body: buildSettingsPayload(settings),
      });
      const normalized = normalizeSettings(updated);
      setSettings(normalized);
      setBaselineSettings(normalized);
      setStatus("设置已保存");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法保存设置");
    }
  }

  function patchSettings<K extends keyof AppSettings>(
    key: K,
    patch: Partial<AppSettings[K]>,
  ) {
    setSettings((current) => ({
      ...current,
      [key]: { ...current[key], ...patch },
    }));
  }

  function renderActiveTab() {
    switch (activeTab) {
      case "xchina":
        return (
          <XChinaSettings
            settings={settings.xchina}
            onChange={(patch) => patchSettings("xchina", patch)}
          />
        );
      case "emby":
        return (
          <EmbySettings
            settings={settings.emby}
            onChange={(patch) => patchSettings("emby", patch)}
          />
        );
      case "storage":
        return (
          <StorageSettings
            settings={settings.storage}
            onChange={(patch) => patchSettings("storage", patch)}
          />
        );
      case "naming":
        return (
          <NamingSettings
            settings={settings.naming}
            onChange={(patch) => patchSettings("naming", patch)}
          />
        );
      case "metadata":
        return (
          <MetadataAssetSettings
            settings={settings.metadata_assets}
            onChange={(patch) => patchSettings("metadata_assets", patch)}
          />
        );
      case "confidence":
        return (
          <ConfidenceSafetySettings
            settings={settings.confidence_safety}
            onChange={(patch) => patchSettings("confidence_safety", patch)}
          />
        );
      case "auth":
        return (
          <AuthSettings
            settings={settings.auth}
            onChange={(patch) => patchSettings("auth", patch)}
          />
        );
    }
  }

  return (
    <form className="page-stack" onSubmit={submit}>
      <Tabs
        activeTab={activeTab}
        ariaLabel="设置分类"
        tabs={settingsTabs}
        onChange={setActiveTab}
      />
      <div className="tab-panel" role="tabpanel">
        {loading ? (
          <LoadingSkeleton rows={5} title="正在加载设置" variant="table" />
        ) : (
          renderActiveTab()
        )}
      </div>

      <SettingsPreflight
        changes={validation.changes}
        errors={validation.errors}
        warnings={validation.warnings}
      />

      <div className="sticky-actions">
        <button disabled={loading || validation.errors.length > 0} type="submit">
          保存设置
        </button>
        {status ? <p className="status">{status}</p> : null}
        {error ? <p className="status error">{error}</p> : null}
      </div>
    </form>
  );
}

function SettingsPreflight({
  changes,
  errors,
  warnings,
}: {
  changes: string[];
  errors: string[];
  warnings: string[];
}) {
  if (!errors.length && !warnings.length && !changes.length) {
    return (
      <EmptyState
        description="当前没有待保存改动。"
        icon="✓"
        title="无改动"
      />
    );
  }

  return (
    <section className="section settings-preflight" aria-labelledby="settings-preflight-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Preflight</p>
          <h2 id="settings-preflight-title">保存前检查</h2>
        </div>
        <span className={`status-pill ${errors.length ? "status-pill-danger" : "status-pill-success"}`}>
          {errors.length ? `${errors.length} 个错误` : "可保存"}
        </span>
      </div>

      {errors.length ? (
        <ErrorNotice title="需要先修正" message="以下错误会阻止保存。" details={<IssueList items={errors} />} />
      ) : null}

      {warnings.length ? (
        <ErrorNotice
          title="建议确认"
          message="这些问题不阻止保存。"
          details={<IssueList items={warnings} />}
          tone="warning"
        />
      ) : null}

      <div className="settings-change-summary">
        <h3>改动摘要</h3>
        {changes.length ? (
          <IssueList items={changes} />
        ) : (
          <p className="muted">没有检测到待保存改动。</p>
        )}
      </div>
    </section>
  );
}

function IssueList({ items }: { items: string[] }) {
  return (
    <ul className="issue-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}
