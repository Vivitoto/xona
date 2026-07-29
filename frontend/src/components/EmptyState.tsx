import type { ReactNode } from "react";
import { CircleDashed, type LucideIcon } from "lucide-react";

interface EmptyStateAction {
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary";
}

interface EmptyStateProps {
  title: string;
  description: ReactNode;
  actions?: EmptyStateAction[];
  icon?: LucideIcon;
}

export function EmptyState({
  title,
  description,
  actions = [],
  icon: Icon = CircleDashed,
}: EmptyStateProps) {
  return (
    <div className="empty-state product-empty-state">
      <span className="empty-state-icon" aria-hidden="true">
        <Icon size={20} strokeWidth={2.2} />
      </span>
      <strong>{title}</strong>
      <span>{description}</span>
      {actions.length ? (
        <div className="button-row">
          {actions.map((action) => (
            <button
              key={action.label}
              className={action.variant === "secondary" ? "secondary" : undefined}
              type="button"
              onClick={action.onClick}
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
