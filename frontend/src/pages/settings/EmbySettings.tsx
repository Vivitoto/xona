import { useState } from "react";

import { apiFetch } from "../../api/client";
import type { AppSettings, EmbyPathMapping } from "../../api/types";
import { CheckboxField, FormField, Section } from "../../components/FormField";
import { isRedactedPlaceholder, redactText } from "../../utils/redaction";

export function EmbySettings({
  settings,
  onChange,
}: {
  settings: AppSettings["emby"];
  onChange: (patch: Partial<AppSettings["emby"]>) => void;
}) {
  const [diagnostic, setDiagnostic] = useState("");

  async function testConnection() {
    const payload: Record<string, unknown> = {
      server_url: settings.server_url || null,
      path_mappings: settings.path_mappings,
    };
    if (!isRedactedPlaceholder(settings.api_key)) {
      payload.api_key = settings.api_key || null;
    }
    const response = await apiFetch<Record<string, unknown>>("/api/emby/test", {
      method: "POST",
      body: payload,
    });
    setDiagnostic(redactText(response));
  }

  function updateMapping(index: number, patch: Partial<EmbyPathMapping>) {
    const next = settings.path_mappings.map((mapping, mappingIndex) =>
      mappingIndex === index ? { ...mapping, ...patch } : mapping,
    );
    onChange({ path_mappings: next });
  }

  return (
    <Section title="Emby">
      <div className="grid three">
        <CheckboxField
          checked={settings.enabled}
          label="启用 Emby 通知"
          onChange={(enabled) => onChange({ enabled })}
        />
        <FormField label="Emby 服务器 URL">
          <input
            value={settings.server_url ?? ""}
            onChange={(event) => onChange({ server_url: event.target.value })}
          />
        </FormField>
        <FormField
          description="保持脱敏占位符不变即可保留已保存的密钥。"
          label="Emby API key"
        >
          <input
            autoComplete="off"
            type="password"
            value={settings.api_key ?? ""}
            onChange={(event) => onChange({ api_key: event.target.value })}
          />
        </FormField>
      </div>
      <CheckboxField
        checked={settings.upload_actor_portraits}
        label="Emby 同步时上传演员头像"
        onChange={(upload_actor_portraits) =>
          onChange({ upload_actor_portraits })
        }
      />
      <div className="subsection">
        <div className="row row-between">
          <h3>Emby 路径映射</h3>
          <button
            type="button"
            onClick={() =>
              onChange({
                path_mappings: [
                  ...settings.path_mappings,
                  { container_root: "", emby_root: "" },
                ],
              })
            }
          >
            添加映射
          </button>
        </div>
        {settings.path_mappings.length ? (
          settings.path_mappings.map((mapping, index) => (
            <div className="grid two mapping-row" key={index}>
              <FormField label="容器根目录">
                <input
                  value={mapping.container_root}
                  onChange={(event) =>
                    updateMapping(index, { container_root: event.target.value })
                  }
                />
              </FormField>
              <FormField label="Emby 可见根目录">
                <input
                  value={mapping.emby_root}
                  onChange={(event) =>
                    updateMapping(index, { emby_root: event.target.value })
                  }
                />
              </FormField>
            </div>
          ))
        ) : (
          <p className="muted">尚未配置路径映射。</p>
        )}
      </div>
      <button type="button" onClick={testConnection}>
        测试 Emby
      </button>
      {diagnostic ? <pre className="diagnostic">{diagnostic}</pre> : null}
    </Section>
  );
}
