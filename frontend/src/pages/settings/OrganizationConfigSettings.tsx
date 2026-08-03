import { useRef, useState } from "react";

import { apiFetch } from "../../api/client";
import type {
  AppSettings,
  OrganizationMode,
  TemplatePreviewResponse,
} from "../../api/types";
import { DirectoryPicker } from "../../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../../components/FormField";
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

export function OrganizationConfigSettings({
  settings,
  onNamingChange,
  onOrganizationDefaultsChange,
  onStorageChange,
}: {
  settings: AppSettings;
  onNamingChange: (patch: Partial<AppSettings["naming"]>) => void;
  onOrganizationDefaultsChange: (
    patch: Partial<AppSettings["organization_defaults"]>,
  ) => void;
  onStorageChange: (patch: Partial<AppSettings["storage"]>) => void;
}) {
  const folderTemplatesRef = useRef<HTMLTextAreaElement>(null);
  const filenameTemplateRef = useRef<HTMLInputElement>(null);
  const [activeTemplateTarget, setActiveTemplateTarget] =
    useState<TemplateTarget>("filename_template");
  const [variablesOpen, setVariablesOpen] = useState(false);
  const [preview, setPreview] = useState<TemplatePreviewResponse | null>(null);
  const [error, setError] = useState("");

  const folderTemplates = settings.organization_defaults.folder_templates.length
    ? settings.organization_defaults.folder_templates
    : settings.naming.folder_templates;
  const filenameTemplate =
    settings.organization_defaults.filename_template || settings.naming.filename_template;

  function addRoot(path: string) {
    if (settings.storage.roots.includes(path) || settings.storage.env_roots.includes(path)) {
      return;
    }
    onStorageChange({ roots: [...settings.storage.roots, path] });
  }

  async function previewTemplate() {
    setError("");
    try {
      setPreview(
        await apiFetch<TemplatePreviewResponse>(
          "/api/settings/templates/preview",
          {
            method: "POST",
            body: {
              folder_templates: folderTemplates,
              filename_template: filenameTemplate,
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
    const currentValue = templateValue(activeTemplateTarget);
    const element = templateElement(activeTemplateTarget);
    const start = element?.selectionStart ?? currentValue.length;
    const end = element?.selectionEnd ?? start;
    const nextValue =
      currentValue.slice(0, start) + variable + currentValue.slice(end);
    const cursor = start + variable.length;

    patchTemplate(activeTemplateTarget, nextValue);

    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(cursor, cursor);
    });
  }

  function templateValue(target: TemplateTarget): string {
    if (target === "folder_templates") {
      return listToLines(folderTemplates);
    }
    return filenameTemplate;
  }

  function templateElement(target: TemplateTarget) {
    if (target === "folder_templates") {
      return folderTemplatesRef.current;
    }
    return filenameTemplateRef.current;
  }

  function patchTemplate(target: TemplateTarget, value: string) {
    if (target === "folder_templates") {
      const nextTemplates = linesToList(value);
      onNamingChange({ folder_templates: nextTemplates });
      onOrganizationDefaultsChange({ folder_templates: nextTemplates });
      return;
    }
    onNamingChange({ filename_template: value });
    onOrganizationDefaultsChange({ filename_template: value });
  }

  return (
    <>
      <Section title="目录配置">
        <div className="settings-subsection">
          <h3>媒体目录</h3>
          <p className="section-lead">
            用于扫描、选择源目录和限制整理路径范围。
          </p>
          {settings.storage.env_roots.length ? (
            <div className="readonly-list" aria-label="容器自动发现的媒体目录">
              <div className="readonly-list-title">容器挂载的媒体目录（自动发现，只读）</div>
              {settings.storage.env_roots.map((root) => (
                <div className="readonly-item" key={root}>
                  <code>{root}</code>
                  <span className="badge">容器挂载</span>
                </div>
              ))}
            </div>
          ) : null}
          <div className="path-field path-field-textarea">
            <FormField
              description="每行一个额外媒体目录；容器挂载目录会显示在上方。"
              label="用户媒体目录"
            >
              <textarea
                placeholder={'/media/downloads\n/mnt/archive'}
                value={listToLines(settings.storage.roots)}
                onChange={(event) =>
                  onStorageChange({ roots: linesToList(event.target.value) })
                }
              />
            </FormField>
            <DirectoryPicker onSelect={addRoot} title="选择媒体目录" />
          </div>
        </div>

        <div className="settings-subsection">
          <h3>整理目标目录</h3>
          <p className="section-lead">
            本地元数据生成的默认写入位置。
          </p>
          <div className="path-field">
            <FormField label="默认目标目录">
              <input
                placeholder="/media/organized"
                value={settings.organization_defaults.destination_directory ?? ""}
                onChange={(event) =>
                  onOrganizationDefaultsChange({
                    destination_directory: event.target.value,
                  })
                }
              />
            </FormField>
            <DirectoryPicker
              initialPath={settings.organization_defaults.destination_directory ?? ""}
              onSelect={(destination_directory) =>
                onOrganizationDefaultsChange({ destination_directory })
              }
              title="选择默认目标目录"
            />
          </div>
        </div>
      </Section>

      <Section title="命名模板">
        <p className="section-lead">
          文件夹模板一行一级目录；文件名模板只写最终文件名。
        </p>
        <div className="grid two">
          <FormField label="文件夹模板">
            <textarea
              placeholder={'{studio}\n{xchina_id} - {title}'}
              ref={folderTemplatesRef}
              value={listToLines(folderTemplates)}
              onFocus={() => setActiveTemplateTarget("folder_templates")}
              onChange={(event) => patchTemplate("folder_templates", event.target.value)}
            />
          </FormField>
          <FormField label="文件名模板">
            <input
              placeholder="{xchina_id} - {title}"
              ref={filenameTemplateRef}
              value={filenameTemplate}
              onFocus={() => setActiveTemplateTarget("filename_template")}
              onChange={(event) => patchTemplate("filename_template", event.target.value)}
            />
          </FormField>
        </div>
        <div className="variable-help">
          <button
            aria-expanded={variablesOpen}
            className="secondary button-compact"
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
        <button className="button-compact" type="button" onClick={previewTemplate}>
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

      <Section title="整理行为">
        <p className="section-lead">本地元数据生成任务的默认文件动作。</p>
        <div className="grid four">
          <FormField label="默认整理模式">
            <select
              value={organizationModeOrCopy(settings.organization_defaults.organization_mode)}
              onChange={(event) =>
                onOrganizationDefaultsChange({
                  organization_mode: event.target.value as OrganizationMode,
                })
              }
            >
              <option value="copy">复制</option>
              <option value="move">移动</option>
              <option value="hardlink">硬链接</option>
              <option value="symlink">符号链接</option>
              <option value="in_place">原地处理</option>
            </select>
          </FormField>
          <FormField label="资源缺失处理">
            <select
              value={settings.organization_defaults.asset_policy}
              onChange={(event) =>
                onOrganizationDefaultsChange({ asset_policy: event.target.value })
              }
            >
              <option value="lenient">缺失继续整理</option>
              <option value="strict">缺失停止整理</option>
            </select>
          </FormField>
          <CheckboxField
            checked={settings.organization_defaults.include_source_snapshot}
            label="默认保存来源页面快照"
            description="额外保存 source-snapshot.html。"
            onChange={(include_source_snapshot) =>
              onOrganizationDefaultsChange({ include_source_snapshot })
            }
          />
        </div>
      </Section>
    </>
  );
}

function organizationModeOrCopy(mode: OrganizationMode): OrganizationMode {
  return mode === "preview" ? "copy" : mode;
}
