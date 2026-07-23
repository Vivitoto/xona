import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskCenterPage } from "./TaskCenterPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TaskCenterPage", () => {
  it("loads details/events, triggers job actions, and redacts timeline secrets", async () => {
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
    fireEvent.change(screen.getByLabelText(/Job ID/i), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "Load job" }));

    expect(await screen.findByText("media-42")).toBeTruthy();
    expect(screen.getAllByText("review_required").length).toBeGreaterThan(0);
    expect(screen.queryByText(/raw-secret/)).toBeNull();
    expect(screen.queryByText(/raw-token/)).toBeNull();
    expect(screen.queryByText(/user:pass/)).toBeNull();
    expect(screen.getByText(/\*{8}/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry Emby" }));

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
