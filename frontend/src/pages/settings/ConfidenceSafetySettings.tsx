import type { AppSettings } from "../../api/types";
import { DirectoryPicker } from "../../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../../components/FormField";

export function ConfidenceSafetySettings({
  settings,
  onChange,
}: {
  settings: AppSettings["confidence_safety"];
  onChange: (patch: Partial<AppSettings["confidence_safety"]>) => void;
}) {
  return (
    <Section title="置信度/安全">
      <div className="grid four">
        <FormField label="置信度阈值">
          <input
            max={100}
            min={0}
            placeholder="92"
            type="number"
            value={settings.confidence_threshold}
            onChange={(event) =>
              onChange({ confidence_threshold: Number(event.target.value) })
            }
          />
        </FormField>
        <CheckboxField
          checked={settings.refuse_destination_collisions}
          label="拒绝目标冲突"
          onChange={(refuse_destination_collisions) =>
            onChange({ refuse_destination_collisions })
          }
        />
        <CheckboxField
          checked={settings.refuse_unresolved_multipart}
          label="拒绝未解决分段文件"
          onChange={(refuse_unresolved_multipart) =>
            onChange({ refuse_unresolved_multipart })
          }
        />
        <div className="path-field">
          <FormField label="安全缓存目录">
            <input
              placeholder="/config/cache/safety"
              value={settings.cache_dir ?? ""}
              onChange={(event) => onChange({ cache_dir: event.target.value })}
            />
          </FormField>
          <DirectoryPicker
            initialPath={settings.cache_dir ?? ""}
            onSelect={(cache_dir) => onChange({ cache_dir })}
            title="选择安全缓存目录"
          />
        </div>
      </div>
    </Section>
  );
}
