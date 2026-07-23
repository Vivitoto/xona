import { useState } from "react";

import { apiFetch } from "../../api/client";
import type { AppSettings } from "../../api/types";
import { CheckboxField, FormField, Section } from "../../components/FormField";
import { isRedactedPlaceholder, redactText } from "../../utils/redaction";

export function XChinaSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["xchina"];
  onChange: (patch: Partial<AppSettings["xchina"]>) => void;
}) {
  const [testQuery, setTestQuery] = useState("sample");
  const [diagnostic, setDiagnostic] = useState("");
  const [useProxyForTest, setUseProxyForTest] = useState(true);

  async function testFlareSolverr() {
    setDiagnostic("");
    const payload: Record<string, unknown> = {
      url: settings.flaresolverr_url || null,
      test_url: settings.base_url || "https://www.xchina.co",
    };
    if (useProxyForTest && !isRedactedPlaceholder(settings.proxy_url)) {
      payload.proxy_url = settings.proxy_url || null;
    }
    const response = await apiFetch<Record<string, unknown>>(
      "/api/settings/flaresolverr/test",
      { method: "POST", body: payload },
    );
    setDiagnostic(redactText(response));
  }

  async function testXChina() {
    setDiagnostic("");
    const response = await apiFetch<Record<string, unknown>>(
      "/api/settings/xchina/test",
      { method: "POST", body: { query: testQuery } },
    );
    setDiagnostic(redactText(response));
  }

  return (
    <Section title="XChina">
      <div className="grid three">
        <FormField label="XChina 基础 URL">
          <input
            value={settings.base_url}
            onChange={(event) => onChange({ base_url: event.target.value })}
          />
        </FormField>
        <FormField
          description="按输入原样保存和调用。客户端不会追加 /v1。"
          label="精确 FlareSolverr 端点"
        >
          <input
            placeholder="http://solver:8191/v1"
            value={settings.flaresolverr_url ?? ""}
            onChange={(event) =>
              onChange({ flaresolverr_url: event.target.value })
            }
          />
        </FormField>
        <FormField
          description="可包含凭据。脱敏占位符仅用于显示。"
          label="代理 URL"
        >
          <input
            value={settings.proxy_url ?? ""}
            onChange={(event) => onChange({ proxy_url: event.target.value })}
          />
        </FormField>
      </div>
      <div className="grid three">
        <FormField label="XChina 缓存目录">
          <input
            value={settings.cache_dir ?? ""}
            onChange={(event) => onChange({ cache_dir: event.target.value })}
          />
        </FormField>
        <FormField label="XChina 测试查询">
          <input
            value={testQuery}
            onChange={(event) => setTestQuery(event.target.value)}
          />
        </FormField>
        <CheckboxField
          checked={useProxyForTest}
          label="连接测试使用代理"
          onChange={setUseProxyForTest}
        />
      </div>
      <div className="button-row">
        <button type="button" onClick={testFlareSolverr}>
          测试 FlareSolverr
        </button>
        <button type="button" onClick={testXChina}>
          测试 XChina
        </button>
      </div>
      {diagnostic ? <pre className="diagnostic">{diagnostic}</pre> : null}
    </Section>
  );
}
