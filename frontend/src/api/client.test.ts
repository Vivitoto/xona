import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./client";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("times out stalled API requests with a visible retryable message", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("Aborted", "AbortError"));
            });
          }),
      ),
    );

    const request = expect(apiFetch("/api/jobs", { timeoutMs: 100 })).rejects.toThrow(
      "API 请求超时，请稍后重试或检查服务是否卡住。",
    );
    await vi.advanceTimersByTimeAsync(100);
    await request;
  });

  it("formats nested backend reason codes as actionable Chinese messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: {
              error: "search_source_unavailable",
              reasons: ["search_source_unavailable"],
            },
          }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(apiFetch("/api/manual/search")).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
      message: "搜索服务暂时不可用，请稍后重试或检查 FlareSolverr / 代理。",
    } satisfies Partial<ApiError>);
  });


  it("turns network failures into a clear backend connection message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(apiFetch("/api/settings")).rejects.toThrow(
      "无法连接 Xona 后端，请检查服务是否正在运行或稍后重试。",
    );
  });

  it("formats validation errors instead of a generic API failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: [
              { loc: ["body", "items"], msg: "List should have at least 1 item" },
            ],
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(apiFetch("/api/local-metadata/batches")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "请求参数不合法：body.items List should have at least 1 item",
    } satisfies Partial<ApiError>);
  });

  it("explains frame cache mismatches as stale/wrong video screenshots", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: { error: "frame_ref_mismatch" } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/local-metadata/cover-preview")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "选择的截图不属于当前视频缓存；请重新生成当前视频截图后再生成封面。",
    } satisfies Partial<ApiError>);
  });

  it("explains cover cache mismatches as stale/wrong video cover assets", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: { error: "cover_ref_mismatch" } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/local-metadata/preview-plan")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "选择的封面素材不属于当前视频缓存；请重新生成当前视频封面预览。",
    } satisfies Partial<ApiError>);
  });

  it("explains non-executable batch execution attempts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: { error: "batch_has_no_executable_items" } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/local-metadata/batches/batch-1/execute")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "当前批量任务没有可执行计划；请确认预览已成功且模式不是“仅预览”。",
    } satisfies Partial<ApiError>);
  });

  it("explains source_missing execute conflicts as stale moved sources", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "source_missing" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/local-metadata/plans/plan-1/execute")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "源视频文件不存在，可能已被前一个移动整理计划移走；请重新扫描目录并重新生成预览。",
    } satisfies Partial<ApiError>);
  });
});
