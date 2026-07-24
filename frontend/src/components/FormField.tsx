import type { ReactNode } from "react";

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  description?: string;
  error?: string;
  children: ReactNode;
}

export function FormField({
  label,
  htmlFor,
  description,
  error,
  children,
}: FormFieldProps) {
  return (
    <div className="field">
      <label className="field-control" htmlFor={htmlFor}>
        <span className="field-label">{label}</span>
        {children}
      </label>
      {description ? <span className="field-help">{description}</span> : null}
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}

export function CheckboxField({
  label,
  description,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="check-field">
      <input
        checked={checked}
        disabled={disabled}
        type="checkbox"
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <span className="field-label">{label}</span>
        {description ? <span className="field-help">{description}</span> : null}
      </span>
    </label>
  );
}

export function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
