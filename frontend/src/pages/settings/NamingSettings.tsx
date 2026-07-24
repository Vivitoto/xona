import { useRef, useState } from "react";

import { apiFetch } from "../../api/client";
import type { AppSettings, TemplatePreviewResponse } from "../../api/types";
import { FormField, Section } from "../../components/FormField";
import { TemplateGuide } from "../../components/TemplateGuide";
import { linesToList, listToLines } from "./settingsForm";

const templateVariables = [
  ["{number}", "番号或作品编号"],
  ["{title}", "作品标题"],
  ["{original_title}", "原始标题"],
  ["{studio}", "制作商"],
  ["{series}", "系列名称"],
  ["{year}", "发布年份"],
  ["{release_date}", "发布日期"],
  ["{actors}", "逗号分隔的演员列表"],
  ["{first_actor}", "第一位演员"],
  ["{source_filename}", "源文件名"],
  ["{xchina_id}", "XChina 作品 ID"],
] as const;

type TemplateTarget = "folder_templates" | "filename_template";

export function NamingSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["naming"];
  onChange: (patch: Partial<AppSettings["naming"]>) => void;
}) {
  const folderTemplatesRef = useRef<HTMLTextAreaElement>(null);
  const filenameTemplateRef = useRef<HTMLInputElement>(null);
  const [activeTemplateTarget, setActiveTemplateTarget] =
    useState<TemplateTarget>("filename_template");
  const [variablesOpen, setVariablesOpen] = useState(false);
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

  function insertVariable(variable: string) {
    const isFolderTarget = activeTemplateTarget === "folder_templates";
    const element = isFolderTarget
      ? folderTemplatesRef.current
      : filenameTemplateRef.current;
    const currentValue = isFolderTarget
      ? listToLines(settings.folder_templates)
      : settings.filename_template;
    const start = element?.selectionStart ?? currentValue.length;
    const end = element?.selectionEnd ?? start;
    const nextValue =
      currentValue.slice(0, start) + variable + currentValue.slice(end);
    const cursor = start + variable.length;

    if (isFolderTarget) {
      onChange({ folder_templates: linesToList(nextValue) });
    } else {
      onChange({ filename_template: nextValue });
    }

    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(cursor, cursor);
    });
  }

  return (
    <Section title="命名模板">
      <div className="grid two">
        <FormField label="文件夹模板">
          <textarea
            placeholder={'{studio}\n{xchina_id} - {title}'}
            ref={folderTemplatesRef}
            value={listToLines(settings.folder_templates)}
            onFocus={() => setActiveTemplateTarget("folder_templates")}
            onChange={(event) =>
              onChange({ folder_templates: linesToList(event.target.value) })
            }
          />
        </FormField>
        <FormField label="文件名模板">
          <input
            placeholder="{xchina_id} - {title}"
            ref={filenameTemplateRef}
            value={settings.filename_template}
            onFocus={() => setActiveTemplateTarget("filename_template")}
            onChange={(event) =>
              onChange({ filename_template: event.target.value })
            }
          />
        </FormField>
      </div>
      <TemplateGuide />
      <div className="variable-help">
        <button
          aria-expanded={variablesOpen}
          className="secondary"
          type="button"
          onClick={() => setVariablesOpen((current) => !current)}
        >
          查看可用变量
        </button>
        {variablesOpen ? (
          <div className="variable-panel">
            {templateVariables.map(([variable, description]) => (
              <div className="variable-row" key={variable}>
                <button
                  className="variable-token"
                  type="button"
                  onClick={() => insertVariable(variable)}
                >
                  {variable}
                </button>
                <span>{description}</span>
              </div>
            ))}
          </div>
        ) : null}
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
