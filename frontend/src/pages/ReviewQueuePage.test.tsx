import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewQueuePage } from "./ReviewQueuePage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReviewQueuePage", () => {
  it("loads review-required jobs and lists confidence and safety reasons", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/jobs?state=review_required",
        response: {
          jobs: [
            {
              id: 21,
              state: "review_required",
              media_identity: "media-review",
              rule_id: null,
              manual: true,
              attempts: 0,
              max_attempts: 3,
              next_run_at: null,
              last_error_code: null,
              payload: {},
              plan_id: "plan-review",
              selected_candidate: { title: "Candidate Title" },
              gate_reasons: ["confidence_below_threshold", "unsafe_path"],
              retryable: true,
              retry_emby_available: false,
            },
          ],
        },
      },
    ]);

    render(<ReviewQueuePage />);

    expect(await screen.findByText("media-review")).toBeTruthy();
    expect(screen.getByText(/confidence_below_threshold/)).toBeTruthy();
    expect(screen.getByText(/unsafe_path/)).toBeTruthy();
    expect(screen.getByText("Candidate Title")).toBeTruthy();
    expect(calls[0]?.url).toBe("/api/jobs?state=review_required");
  });
});
