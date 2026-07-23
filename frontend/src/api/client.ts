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
