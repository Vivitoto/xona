import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { AppSettings } from "../api/types";
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
} from "./settings/settingsForm";

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(emptySettings);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiFetch<AppSettings>("/api/settings")
      .then((payload) => {
        if (active) {
          setSettings(normalizeSettings(payload));
        }
      })
      .catch((exc) => {
        if (active) {
          setError(exc instanceof Error ? exc.message : "无法加载设置");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("");
    setError("");
    try {
      const updated = await apiFetch<AppSettings>("/api/settings", {
        method: "PUT",
        body: buildSettingsPayload(settings),
      });
      setSettings(normalizeSettings(updated));
      setStatus("设置已保存");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法保存设置");
    }
  }

  return (
    <form className="page-stack" onSubmit={submit}>
      <StorageSettings
        settings={settings.storage}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            storage: { ...current.storage, ...patch },
          }))
        }
      />
      <XChinaSettings
        settings={settings.xchina}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            xchina: { ...current.xchina, ...patch },
          }))
        }
      />
      <EmbySettings
        settings={settings.emby}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            emby: { ...current.emby, ...patch },
          }))
        }
      />
      <NamingSettings
        settings={settings.naming}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            naming: { ...current.naming, ...patch },
          }))
        }
      />
      <MetadataAssetSettings
        settings={settings.metadata_assets}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            metadata_assets: { ...current.metadata_assets, ...patch },
          }))
        }
      />
      <ConfidenceSafetySettings
        settings={settings.confidence_safety}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            confidence_safety: { ...current.confidence_safety, ...patch },
          }))
        }
      />
      <AuthSettings
        settings={settings.auth}
        onChange={(patch) =>
          setSettings((current) => ({
            ...current,
            auth: { ...current.auth, ...patch },
          }))
        }
      />
      <div className="sticky-actions">
        <button type="submit">保存设置</button>
        {status ? <p className="status">{status}</p> : null}
        {error ? <p className="status error">{error}</p> : null}
      </div>
    </form>
  );
}
