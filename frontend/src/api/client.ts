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
    if (exc instanceof TypeError) {
      throw new Error("无法连接 Xona 后端，请检查服务是否正在运行或稍后重试。");
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
  const validationMessage = firstValidationMessage(detail);
  if (validationMessage) {
    return `请求参数不合法：${validationMessage}`;
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
    const label = apiReasonLabel(code);
    if (label) {
      return label;
    }
  }
  return null;
}

function firstValidationMessage(value: unknown): string | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (Array.isArray(record.detail)) {
    const first = record.detail.find(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === "object" && typeof (item as Record<string, unknown>).msg === "string",
    );
    if (first && typeof first.msg === "string") {
      const location = Array.isArray(first.loc)
        ? first.loc.filter((part) => typeof part === "string" || typeof part === "number").join(".")
        : "";
      return location ? `${location} ${first.msg}` : first.msg;
    }
  }
  if ("detail" in record) {
    return firstValidationMessage(record.detail);
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
  batch_has_no_failed_items: "当前批量任务没有失败条目可重试。",
  batch_has_no_executable_items: "当前批量任务没有可执行计划；请确认预览已成功且模式不是“仅预览”。",
  batch_manager_unavailable: "批量任务服务未启动，请重启 Xona 或检查后台服务。",
  batch_not_found: "找不到这个批量任务，可能已被清理或页面数据已过期。",
  batch_not_ready_to_execute: "批量预览还未完成，请等待所有条目结束后再执行。",
  cache_ref_not_found: "缓存文件不存在，可能已被清理；请重新生成截图/封面预览。",
  candidate_detail_unavailable: "详情页暂时无法解析，已无法获取完整候选详情；请稍后重试或换一个候选/详情 URL。",
  cover_generation_failed: "封面生成失败；请检查截图是否足够、字体/模板是否可用后重试。",
  cover_ref_mismatch: "选择的封面素材不属于当前视频缓存；请重新生成当前视频封面预览。",
  destination_outside_storage_root: "目标目录不在允许的媒体库根目录内，请换到已配置的存储路径。",
  frame_required: "截图不足或未选择足够截图，请先生成并选择至少 9 张不同截图。",
  frame_ref_mismatch: "选择的截图不属于当前视频缓存；请重新生成当前视频截图后再生成封面。",
  invalid_cache_ref: "缓存引用无效；请重新生成截图/封面预览。",
  path_outside_storage_root: "路径不在允许的媒体库根目录内，请选择已配置存储路径下的视频。",
  plan_approval_required: "执行整理计划前需要确认授权。",
  plan_not_completed: "整理计划尚未完成，暂时不能清理缓存。",
  plan_not_found: "找不到整理计划，可能已过期；请重新生成预览。",
  plan_rejected: "整理计划被安全规则拒绝，请查看冲突/警告后调整目标路径或模式。",
  plan_version_mismatch: "整理计划版本已变化，请刷新或重新生成预览后再执行。",
  scan_failed: "目录扫描失败，请确认路径存在且 Xona 有读取权限。",
  source_already_planned: "这个源文件已有待执行的移动整理计划；请先执行或删除旧计划后再重新生成预览。",
  source_missing: "源视频文件不存在，可能已被前一个移动整理计划移走；请重新扫描目录并重新生成预览。",
  search_source_unavailable: "搜索服务暂时不可用，请稍后重试或检查 FlareSolverr / 代理。",
  video_not_found: "视频文件不存在或 Xona 无法读取；请重新选择文件或检查权限。",
};

function apiReasonLabel(code: string): string | null {
  const exact = apiReasonLabels[code];
  if (exact) {
    return exact;
  }
  if (code.startsWith("plan_not_executable:")) {
    return "当前整理计划不可执行，请重新生成预览或确认模式不是“仅预览”。";
  }
  return null;
}
