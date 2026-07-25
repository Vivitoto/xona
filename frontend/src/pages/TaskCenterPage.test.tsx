import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskCenterPage } from "./TaskCenterPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TaskCenterPage", () => {
  it("loads details/events, triggers job actions, and renders compact progress", async () => {
    const { calls } = installFetchMock([
      { path: "/api/jobs/42", response: jobFixture() },
      {
        path: "/api/jobs/42/events",
        response: {
          events: [
            {
              id: 2,
              job_id: 42,
              from_state: "searching",
              to_state: "review_required",
              payload: {
                api_key: "raw-secret",
                proxy: "http://user:pass@proxy.test:8080",
                header: "Bearer raw-token",
              },
            },
          ],
        },
      },
      { method: "POST", path: "/api/jobs/42/retry", response: { job: jobFixture("searching") } },
      { method: "POST", path: "/api/jobs/42/cancel", response: { job: jobFixture("cancelled") } },
      { method: "POST", path: "/api/jobs/42/retry-emby", response: { job_id: 42, state: "notifying_emby" } },
    ]);

    render(<TaskCenterPage />);
    fireEvent.change(screen.getByLabelText(/任务 ID/i), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "加载任务" }));

    expect((await screen.findAllByText("media-42")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("等待人工复核").length).toBeGreaterThan(0);
    expect(screen.queryByText("review_required")).toBeNull();
    const progressLog = screen.getByLabelText("任务进度日志");
    expect(progressLog).toHaveTextContent("等待人工复核");
    expect(screen.queryByText(/raw-secret/)).toBeNull();
    expect(screen.queryByText(/raw-token/)).toBeNull();
    expect(screen.queryByText(/user:pass/)).toBeNull();
    expect(progressLog).not.toHaveTextContent("api_key");
    expect(progressLog).not.toHaveTextContent("Bearer");

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(screen.getByRole("button", { name: "重试 Emby" }));

    await waitFor(() => {
      expect(calls.some((call) => call.url === "/api/jobs/42/retry")).toBe(true);
      expect(calls.some((call) => call.url === "/api/jobs/42/cancel")).toBe(true);
      expect(calls.some((call) => call.url === "/api/jobs/42/retry-emby")).toBe(true);
    });
  });
});

function jobFixture(state = "review_required") {
  return {
    id: 42,
    state,
    media_identity: "media-42",
    rule_id: null,
    manual: true,
    attempts: 1,
    max_attempts: 3,
    next_run_at: null,
    last_error_code: null,
    payload: {},
    plan_id: "plan-42",
    selected_candidate: { title: "Candidate" },
    gate_reasons: ["confidence_below_threshold"],
    retryable: true,
    retry_emby_available: true,
  };
}
