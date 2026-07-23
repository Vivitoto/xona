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
    <Section title="Metadata/Assets">
      <div className="grid four">
        <CheckboxField
          checked={settings.write_nfo}
          label="Write NFO metadata"
          onChange={(write_nfo) => onChange({ write_nfo })}
        />
        <CheckboxField
          checked={settings.include_source_snapshot}
          label="Include source snapshot"
          onChange={(include_source_snapshot) =>
            onChange({ include_source_snapshot })
          }
        />
        <FormField label="Asset policy">
          <select
            value={settings.asset_policy}
            onChange={(event) => onChange({ asset_policy: event.target.value })}
          >
            <option value="lenient">Lenient</option>
            <option value="strict">Strict</option>
          </select>
        </FormField>
        <FormField label="Max asset bytes">
          <input
            min={1}
            type="number"
            value={settings.max_asset_bytes}
            onChange={(event) =>
              onChange({ max_asset_bytes: Number(event.target.value) })
            }
          />
        </FormField>
      </div>
    </Section>
  );
}
