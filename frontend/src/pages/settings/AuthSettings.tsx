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
    <Section title="认证">
      <div className="grid three">
        <CheckboxField
          checked={settings.enabled}
          label="API 路由需要认证"
          onChange={(enabled) => onChange({ enabled })}
        />
        <FormField label="用户名">
          <input
            autoComplete="username"
            placeholder="admin"
            value={settings.username ?? ""}
            onChange={(event) => onChange({ username: event.target.value })}
          />
        </FormField>
        <FormField
          description="密码修改需使用认证设置流程；占位符不会通过设置提交。"
          label="密码占位符"
        >
          <input readOnly type="password" value="********" />
        </FormField>
      </div>
    </Section>
  );
}
