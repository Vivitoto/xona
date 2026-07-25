import type { AppSettings, OrganizationMode } from "../../api/types";
import { DirectoryPicker } from "../../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../../components/FormField";
import { linesToList, listToLines } from "./settingsForm";

export function OrganizationDefaultsSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["organization_defaults"];
  onChange: (patch: Partial<AppSettings["organization_defaults"]>) => void;
}) {
  return (
    <Section title="全局整理">
      <div className="grid four">
        <div className="path-field">
          <FormField label="默认目标目录">
            <input
              placeholder="/media/organized"
              value={settings.destination_directory ?? ""}
              onChange={(event) =>
                onChange({ destination_directory: event.target.value })
              }
            />
          </FormField>
          <DirectoryPicker
            initialPath={settings.destination_directory ?? ""}
            onSelect={(destination_directory) => onChange({ destination_directory })}
            title="选择默认目标目录"
          />
        </div>
        <FormField label="默认整理模式">
          <select
            value={organizationModeOrCopy(settings.organization_mode)}
            onChange={(event) =>
              onChange({ organization_mode: event.target.value as OrganizationMode })
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
            value={settings.asset_policy}
            onChange={(event) => onChange({ asset_policy: event.target.value })}
          >
            <option value="lenient">缺失继续整理</option>
            <option value="strict">缺失停止整理</option>
          </select>
        </FormField>
        <CheckboxField
          checked={settings.include_source_snapshot}
          label="默认包含源快照"
          onChange={(include_source_snapshot) =>
            onChange({ include_source_snapshot })
          }
        />
      </div>
      <div className="grid two">
        <FormField label="默认文件夹模板">
          <textarea
            placeholder={'{studio}\n{xchina_id} - {title}'}
            value={listToLines(settings.folder_templates)}
            onChange={(event) =>
              onChange({ folder_templates: linesToList(event.target.value) })
            }
          />
        </FormField>
        <FormField label="默认文件名模板">
          <input
            placeholder="{xchina_id} - {title}"
            value={settings.filename_template}
            onChange={(event) =>
              onChange({ filename_template: event.target.value })
            }
          />
        </FormField>
      </div>
    </Section>
  );
}

function organizationModeOrCopy(mode: OrganizationMode): OrganizationMode {
  return mode === "preview" ? "copy" : mode;
}
