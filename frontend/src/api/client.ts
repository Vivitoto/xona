type JsonBody = Record<string, unknown> | unknown[];

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(formatDetail(detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | JsonBody | null;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  let body = options.body;

  if (isJsonBody(body)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers,
    body: body as BodyInit | null | undefined,
  });

  const payload = await readPayload(response);
  if (!response.ok) {
    throw new ApiError(response.status, payload);
  }

  return payload as T;
}

async function readPayload(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  return text ? { detail: text } : null;
}

function isJsonBody(body: ApiFetchOptions["body"]): body is JsonBody {
  return (
    body !== null &&
    body !== undefined &&
    typeof body === "object" &&
    !(body instanceof Blob) &&
    !(body instanceof FormData) &&
    !(body instanceof URLSearchParams) &&
    !(body instanceof ArrayBuffer)
  );
}

function formatDetail(detail: unknown): string {
  const reasonLabel = firstReasonLabel(detail);
  if (reasonLabel) {
    return reasonLabel;
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (
    detail &&
    typeof detail === "object" &&
    "detail" in detail &&
    typeof detail.detail === "string"
  ) {
    return detail.detail;
  }
  return "API 请求失败";
}

function firstReasonLabel(detail: unknown): string | null {
  const codes = collectReasonCodes(detail);
  for (const code of codes) {
    const label = apiReasonLabels[code];
    if (label) {
      return label;
    }
  }
  return null;
}

function collectReasonCodes(value: unknown): string[] {
  if (typeof value === "string") {
    return [value];
  }
  if (!value || typeof value !== "object") {
    return [];
  }
  const record = value as Record<string, unknown>;
  const codes: string[] = [];
  if (typeof record.error === "string") {
    codes.push(record.error);
  }
  if (Array.isArray(record.reasons)) {
    codes.push(...record.reasons.filter((reason): reason is string => typeof reason === "string"));
  }
  if ("detail" in record) {
    codes.push(...collectReasonCodes(record.detail));
  }
  return codes;
}

const apiReasonLabels: Record<string, string> = {
  candidate_detail_unavailable: "详情页暂时无法解析，已无法获取完整候选详情；请稍后重试或换一个候选/详情 URL。",
  search_source_unavailable: "搜索服务暂时不可用，请稍后重试或检查 FlareSolverr / 代理。",
};
