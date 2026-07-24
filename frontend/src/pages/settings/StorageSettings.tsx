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
    <Section title="媒体目录">
      {settings.env_roots.length ? (
        <div className="readonly-list" aria-label="容器自动发现的媒体目录">
          <div className="readonly-list-title">容器挂载的媒体目录（自动发现，只读）</div>
          {settings.env_roots.map((root) => (
            <div className="readonly-item" key={root}>
              <code>{root}</code>
              <span className="badge">容器挂载</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="path-field path-field-textarea">
        <FormField
          description="每行一个额外媒体目录。容器已挂载的目录会在上方自动发现并只读展示，不需要重复填写。"
          label="用户媒体目录"
        >
          <textarea
            placeholder={'/media/downloads\n/mnt/archive'}
            value={listToLines(settings.roots)}
            onChange={(event) =>
              onChange({ roots: linesToList(event.target.value) })
            }
          />
        </FormField>
        <DirectoryPicker onSelect={addRoot} title="选择媒体目录" />
      </div>
    </Section>
  );
}
