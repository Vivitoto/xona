import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
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
});
