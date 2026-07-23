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
        <FormField label="XChina base URL">
          <input
            value={settings.base_url}
            onChange={(event) => onChange({ base_url: event.target.value })}
          />
        </FormField>
        <FormField
          description="Stored and called exactly as entered. The client never appends /v1."
          label="Exact FlareSolverr endpoint"
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
          description="May include credentials. Redacted placeholders are display-only."
          label="Proxy URL"
        >
          <input
            value={settings.proxy_url ?? ""}
            onChange={(event) => onChange({ proxy_url: event.target.value })}
          />
        </FormField>
      </div>
      <div className="grid three">
        <FormField label="XChina cache directory">
          <input
            value={settings.cache_dir ?? ""}
            onChange={(event) => onChange({ cache_dir: event.target.value })}
          />
        </FormField>
        <FormField label="XChina test query">
          <input
            value={testQuery}
            onChange={(event) => setTestQuery(event.target.value)}
          />
        </FormField>
        <CheckboxField
          checked={useProxyForTest}
          label="Use proxy for connector test"
          onChange={setUseProxyForTest}
        />
      </div>
      <div className="button-row">
        <button type="button" onClick={testFlareSolverr}>
          Test FlareSolverr
        </button>
        <button type="button" onClick={testXChina}>
          Test XChina
        </button>
      </div>
      {diagnostic ? <pre className="diagnostic">{diagnostic}</pre> : null}
    </Section>
  );
}
