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
