import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HistoryRollbackPage } from "./HistoryRollbackPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HistoryRollbackPage", () => {
  it("loads history, shows verification, and displays unsafe rollback refusals", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/history/plans",
        response: {
          plans: [
            {
              plan_id: "plan-history",
              job_id: 5,
              mode: "copy",
              status: "completed",
              verification_status: "externally_modified",
              target_paths: ["/media/organized/Movie/Movie.mkv"],
              created_at: "2026-07-23T00:00:00Z",
            },
          ],
        },
      },
      {
        method: "POST",
        path: "/api/plans/plan-history/rollback",
        status: 409,
        response: {
          detail: {
            error: "rollback_refused",
            reason: "target externally modified",
          },
        },
      },
    ]);

    render(<HistoryRollbackPage />);

    expect(await screen.findByText("externally_modified")).toBeTruthy();
    expect(screen.getAllByText("/media/organized/Movie/Movie.mkv").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Rollback" }));
    expect(await screen.findByText(/Rollback refused: target externally modified/)).toBeTruthy();
    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/plans/plan-history/rollback",
      ),
    ).toBe(true);
  });
});
