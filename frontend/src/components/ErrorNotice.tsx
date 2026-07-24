import type { ReactNode } from "react";

export interface ErrorNoticeAction {
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary";
}

interface ErrorNoticeProps {
  title?: string;
  message: ReactNode;
  details?: ReactNode;
  actions?: ErrorNoticeAction[];
  tone?: "error" | "warning";
}

export function ErrorNotice({
  title = "操作失败",
  message,
  details,
  actions = [],
  tone = "error",
}: ErrorNoticeProps) {
  return (
    <div className={`error-notice error-notice-${tone}`} role="alert">
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
        {details ? <div className="error-notice-details">{details}</div> : null}
      </div>
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

export function describeError(error: unknown, fallback = "发生未知错误"): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}
