import type { AppSettings } from "../../api/types";
import { DirectoryPicker } from "../../components/DirectoryPicker";
import { FormField, Section } from "../../components/FormField";
import { linesToList, listToLines } from "./settingsForm";

export function StorageSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["storage"];
  onChange: (patch: Partial<AppSettings["storage"]>) => void;
}) {
  function addRoot(path: string) {
    if (settings.roots.includes(path) || settings.env_roots.includes(path)) {
      return;
    }
    onChange({ roots: [...settings.roots, path] });
  }

  return (
    <Section title="存储根">
      {settings.env_roots.length ? (
        <div className="readonly-list" aria-label="环境变量配置的存储根">
          <div className="readonly-list-title">环境变量配置的存储根（只读）</div>
          {settings.env_roots.map((root) => (
            <div className="readonly-item" key={root}>
              <code>{root}</code>
              <span className="badge">环境变量</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="path-field path-field-textarea">
        <FormField
          description="每行一个用户可管理的挂载根目录。环境变量配置的根目录会在上方只读展示，不会在保存时被覆盖。"
          label="用户存储根"
        >
          <textarea
            placeholder={'/media/downloads\n/mnt/archive'}
            value={listToLines(settings.roots)}
            onChange={(event) =>
              onChange({ roots: linesToList(event.target.value) })
            }
          />
        </FormField>
        <DirectoryPicker onSelect={addRoot} title="选择存储根目录" />
      </div>
    </Section>
  );
}
