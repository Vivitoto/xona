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
    <Section title="Confidence/Safety">
      <div className="grid four">
        <FormField label="Confidence threshold">
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
          label="Refuse destination collisions"
          onChange={(refuse_destination_collisions) =>
            onChange({ refuse_destination_collisions })
          }
        />
        <CheckboxField
          checked={settings.refuse_unresolved_multipart}
          label="Refuse unresolved multipart"
          onChange={(refuse_unresolved_multipart) =>
            onChange({ refuse_unresolved_multipart })
          }
        />
        <FormField label="Safety cache directory">
          <input
            value={settings.cache_dir ?? ""}
            onChange={(event) => onChange({ cache_dir: event.target.value })}
          />
        </FormField>
      </div>
    </Section>
  );
}
