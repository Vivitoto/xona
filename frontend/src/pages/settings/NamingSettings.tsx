import { useState } from "react";

import { apiFetch } from "../../api/client";
import type { AppSettings, TemplatePreviewResponse } from "../../api/types";
import { FormField, Section } from "../../components/FormField";
import { linesToList, listToLines } from "./settingsForm";

export function NamingSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["naming"];
  onChange: (patch: Partial<AppSettings["naming"]>) => void;
}) {
  const [preview, setPreview] = useState<TemplatePreviewResponse | null>(null);
  const [error, setError] = useState("");

  async function previewTemplate() {
    setError("");
    try {
      setPreview(
        await apiFetch<TemplatePreviewResponse>(
          "/api/settings/templates/preview",
          {
            method: "POST",
            body: {
              folder_templates: settings.folder_templates,
              filename_template: settings.filename_template,
              context: {
                studio: "Studio",
                title: "Sample Work",
                xchina_id: "XC-001",
                source_filename: "Sample.Work.mkv",
              },
            },
          },
        ),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Template preview failed");
    }
  }

  return (
    <Section title="Naming Templates">
      <div className="grid two">
        <FormField label="Folder templates">
          <textarea
            value={listToLines(settings.folder_templates)}
            onChange={(event) =>
              onChange({ folder_templates: linesToList(event.target.value) })
            }
          />
        </FormField>
        <FormField label="Filename template">
          <input
            value={settings.filename_template}
            onChange={(event) =>
              onChange({ filename_template: event.target.value })
            }
          />
        </FormField>
      </div>
      <button type="button" onClick={previewTemplate}>
        Preview naming template
      </button>
      {error ? <p className="status error">{error}</p> : null}
      {preview ? (
        <dl className="metadata-list">
          <div>
            <dt>Folder path</dt>
            <dd>{preview.folder_path ?? "Not generated"}</dd>
          </div>
          <div>
            <dt>Filename</dt>
            <dd>{preview.filename ?? "Not generated"}</dd>
          </div>
          <div>
            <dt>Warnings</dt>
            <dd>{preview.warnings.join(", ") || "None"}</dd>
          </div>
          <div>
            <dt>Validation errors</dt>
            <dd>{preview.validation_errors.join(", ") || "None"}</dd>
          </div>
        </dl>
      ) : null}
    </Section>
  );
}
