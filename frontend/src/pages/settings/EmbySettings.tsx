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
          label="Enable Emby notification"
          onChange={(enabled) => onChange({ enabled })}
        />
        <FormField label="Emby server URL">
          <input
            value={settings.server_url ?? ""}
            onChange={(event) => onChange({ server_url: event.target.value })}
          />
        </FormField>
        <FormField
          description="Leave the redacted placeholder unchanged to keep the saved key."
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
        label="Upload actor portraits during Emby sync"
        onChange={(upload_actor_portraits) =>
          onChange({ upload_actor_portraits })
        }
      />
      <div className="subsection">
        <div className="row row-between">
          <h3>Emby path mappings</h3>
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
            Add mapping
          </button>
        </div>
        {settings.path_mappings.length ? (
          settings.path_mappings.map((mapping, index) => (
            <div className="grid two mapping-row" key={index}>
              <FormField label="Container root">
                <input
                  value={mapping.container_root}
                  onChange={(event) =>
                    updateMapping(index, { container_root: event.target.value })
                  }
                />
              </FormField>
              <FormField label="Emby visible root">
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
          <p className="muted">No path mappings configured.</p>
        )}
      </div>
      <button type="button" onClick={testConnection}>
        Test Emby
      </button>
      {diagnostic ? <pre className="diagnostic">{diagnostic}</pre> : null}
    </Section>
  );
}
