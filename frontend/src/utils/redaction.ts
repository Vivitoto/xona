import { REDACTED_PLACEHOLDER } from "../api/types";

const SECRET_KEY_PATTERN =
  /\b(api[_-]?key|token|cookie|password|secret|authorization|bearer)\b/i;

export function redactText(value: unknown): string {
  const raw = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return raw
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, `Bearer ${REDACTED_PLACEHOLDER}`)
    .replace(
      /(["']?)(api[_-]?key|token|cookie|password|secret)(\1)\s*[:=]\s*["']?[^"',\s}]+["']?/gi,
      (_match, quote: string, key: string) =>
        quote ? `${quote}${key}${quote}: "${REDACTED_PLACEHOLDER}"` : `${key}: ${REDACTED_PLACEHOLDER}`,
    )
    .replace(
      /(https?:\/\/)([^:/@\s]+):([^@/\s]+)@/gi,
      `$1${REDACTED_PLACEHOLDER}:${REDACTED_PLACEHOLDER}@`,
    );
}

export function redactObject<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((entry) => redactObject(entry)) as T;
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [
        key,
        SECRET_KEY_PATTERN.test(key) ? REDACTED_PLACEHOLDER : redactObject(entry),
      ]),
    ) as T;
  }
  if (typeof value === "string") {
    return redactText(value) as T;
  }
  return value;
}

export function isRedactedPlaceholder(value: string | null | undefined): boolean {
  return Boolean(value && value.includes(REDACTED_PLACEHOLDER));
}
