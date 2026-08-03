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
          label="启用登录保护"
          description="API 和管理操作需要登录。"
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
          description="不会显示或提交已保存密码。"
          label="已配置密码"
        >
          <input readOnly type="password" value="********" />
        </FormField>
      </div>
    </Section>
  );
}
