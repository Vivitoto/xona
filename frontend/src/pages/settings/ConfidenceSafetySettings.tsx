import type { AppSettings } from "../../api/types";
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
        <FormField label="安全缓存目录">
          <input
            value={settings.cache_dir ?? ""}
            onChange={(event) => onChange({ cache_dir: event.target.value })}
          />
        </FormField>
      </div>
    </Section>
  );
}
