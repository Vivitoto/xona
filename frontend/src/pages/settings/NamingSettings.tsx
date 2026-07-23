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
      setError(exc instanceof Error ? exc.message : "模板预览失败");
    }
  }

  return (
    <Section title="命名模板">
      <div className="grid two">
        <FormField label="文件夹模板">
          <textarea
            value={listToLines(settings.folder_templates)}
            onChange={(event) =>
              onChange({ folder_templates: linesToList(event.target.value) })
            }
          />
        </FormField>
        <FormField label="文件名模板">
          <input
            value={settings.filename_template}
            onChange={(event) =>
              onChange({ filename_template: event.target.value })
            }
          />
        </FormField>
      </div>
      <button type="button" onClick={previewTemplate}>
        预览命名模板
      </button>
      {error ? <p className="status error">{error}</p> : null}
      {preview ? (
        <dl className="metadata-list">
          <div>
            <dt>文件夹路径</dt>
            <dd>{preview.folder_path ?? "未生成"}</dd>
          </div>
          <div>
            <dt>文件名</dt>
            <dd>{preview.filename ?? "未生成"}</dd>
          </div>
          <div>
            <dt>警告</dt>
            <dd>{preview.warnings.join(", ") || "无"}</dd>
          </div>
          <div>
            <dt>验证错误</dt>
            <dd>{preview.validation_errors.join(", ") || "无"}</dd>
          </div>
        </dl>
      ) : null}
    </Section>
  );
}
