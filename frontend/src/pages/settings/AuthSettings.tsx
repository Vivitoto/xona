import type { AppSettings } from "../../api/types";
import { CheckboxField, FormField, Section } from "../../components/FormField";

export function AuthSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["auth"];
  onChange: (patch: Partial<AppSettings["auth"]>) => void;
}) {
  return (
    <Section title="Authentication">
      <div className="grid three">
        <CheckboxField
          checked={settings.enabled}
          label="Require authentication for API routes"
          onChange={(enabled) => onChange({ enabled })}
        />
        <FormField label="Username">
          <input
            autoComplete="username"
            value={settings.username ?? ""}
            onChange={(event) => onChange({ username: event.target.value })}
          />
        </FormField>
        <FormField
          description="Password changes use the auth setup flow; placeholders are never submitted in settings."
          label="Password placeholder"
        >
          <input readOnly type="password" value="********" />
        </FormField>
      </div>
    </Section>
  );
}
