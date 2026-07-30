type JsonBody = Record<string, unknown> | unknown[];
const DEFAULT_API_TIMEOUT_MS = 20_000;

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
  timeoutMs?: number;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { body: requestBody, timeoutMs = DEFAULT_API_TIMEOUT_MS, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers);
  let body = requestBody;
  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0
      ? window.setTimeout(() => controller.abort("timeout"), timeoutMs)
      : null;
  const abortFromCaller = () => controller.abort(fetchOptions.signal?.reason);

  if (fetchOptions.signal) {
    if (fetchOptions.signal.aborted) {
      abortFromCaller();
    } else {
      fetchOptions.signal.addEventListener("abort", abortFromCaller, { once: true });
    }
  }

  if (isJsonBody(body)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  try {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...fetchOptions,
      headers,
      body: body as BodyInit | null | undefined,
      signal: controller.signal,
    });

    const payload = await readPayload(response);
    if (!response.ok) {
      throw new ApiError(response.status, payload);
    }

    return payload as T;
  } catch (exc) {
    if (controller.signal.aborted && controller.signal.reason === "timeout") {
      throw new Error("API 请求超时，请稍后重试或检查服务是否卡住。");
    }
    throw exc;
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
    fetchOptions.signal?.removeEventListener("abort", abortFromCaller);
  }
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
  source_already_planned: "这个源文件已有待执行的移动整理计划；请先执行或删除旧计划后再重新生成预览。",
  source_missing: "源视频文件不存在，可能已被前一个移动整理计划移走；请重新扫描目录并重新生成预览。",
  search_source_unavailable: "搜索服务暂时不可用，请稍后重试或检查 FlareSolverr / 代理。",
};
