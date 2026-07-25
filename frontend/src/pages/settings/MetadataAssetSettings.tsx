import type { AppSettings } from "../../api/types";
import { CheckboxField, FormField, Section } from "../../components/FormField";

export function MetadataAssetSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["metadata_assets"];
  onChange: (patch: Partial<AppSettings["metadata_assets"]>) => void;
}) {
  return (
    <Section title="元数据/资源">
      <div className="grid four">
        <CheckboxField
          checked={settings.write_nfo}
          label="写入 .nfo 元数据"
          onChange={(write_nfo) => onChange({ write_nfo })}
        />
        <CheckboxField
          checked={settings.include_source_snapshot}
          label="包含源快照"
          onChange={(include_source_snapshot) =>
            onChange({ include_source_snapshot })
          }
        />
        <FormField label="资源缺失处理">
          <select
            value={settings.asset_policy}
            onChange={(event) => onChange({ asset_policy: event.target.value })}
          >
            <option value="lenient">缺失继续整理</option>
            <option value="strict">缺失停止整理</option>
          </select>
        </FormField>

      </div>
    </Section>
  );
}
