import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskCenterPage } from "./TaskCenterPage";
import type { OperationPlan, OrganizeRecordRead } from "../api/types";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("TaskCenterPage", () => {
  it("loads organize records, filters, opens detail, reruns, and rolls back", async () => {
    const onRerun = vi.fn();
    let rolledBack = false;
    const { calls } = installFetchMock([
      {
        path: (url) => url.startsWith("/api/organize-records?"),
        response: () => ({
          records: [
            recordFixture({
              status: rolledBack ? "rolled_back" : "completed",
              can_rollback: !rolledBack,
            }),
            recordFixture({
              record_id: "planrow-7",
              display_index: "#7",
              job_id: null,
              plan_id: "plan-7",
              short_plan_id: "plan-7",
              name: "Externally Modified",
              verification_status: "externally_modified",
              status: "completed",
              can_rollback: false,
            }),
          ],
        }),
      },
      {
        path: "/api/organize-records/job-42",
        response: recordFixture({ plan: planFixture() }),
      },
      {
        method: "POST",
        path: "/api/organize-records/job-42/rollback",
        response: () => {
          rolledBack = true;
          return {
            record_id: "job-42",
            plan_id: "plan-42",
            status: "rolled_back",
            reversed_steps: ["plan-42:0001"],
            refusal_reason: null,
          };
        },
      },
    ]);

    render(<TaskCenterPage onRerun={onRerun} />);

    expect(await screen.findByRole("button", { name: "#42" })).toBeTruthy();
    expect(screen.getAllByText("整理记录").length).toBeGreaterThan(0);
    expect(calls[0]?.url).toBe("/api/organize-records?limit=50");

    fireEvent.change(screen.getByLabelText("状态"), { target: { value: "rollbackable" } });
    await waitFor(() => {
      expect(
        calls.some((call) => call.url === "/api/organize-records?limit=50&status=rollbackable"),
      ).toBe(true);
    });

    fireEvent.change(screen.getByLabelText("状态"), { target: { value: "modified" } });
    await waitFor(() => {
      expect(
        calls.some((call) => call.url === "/api/organize-records?limit=50&status=modified"),
      ).toBe(true);
    });
    expect(screen.getByText("完成/目标变更")).toBeTruthy();
    expect(screen.queryByText("目标被外部修改")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "#42" }));

    expect(await screen.findByText("计划 plan-42")).toBeTruthy();
    expect(screen.getAllByText("Movie 42").length).toBeGreaterThan(0);
    expect(calls.some((call) => call.url === "/api/organize-records/job-42")).toBe(true);

    fireEvent.click(enabledButton("重新整理"));
    expect(localStorage.getItem("xona-rerun-video-path")).toBe(
      "/media/organized/Movie 42/Movie 42.mkv",
    );
    expect(onRerun).toHaveBeenCalledWith("/media/organized/Movie 42/Movie 42.mkv");

    fireEvent.click(enabledButton("回滚"));
    await waitFor(() => {
      expect(calls.some((call) => call.url === "/api/organize-records/job-42/rollback")).toBe(true);
      expect(
        calls.filter(
          (call) => call.url === "/api/organize-records?limit=50&status=modified",
        ).length,
      ).toBeGreaterThan(1);
    });
  });
});

function enabledButton(name: string): HTMLElement {
  const button = screen
    .getAllByRole("button", { name })
    .find((item) => !item.hasAttribute("disabled"));
  if (!button) {
    throw new Error(`No enabled button named ${name}`);
  }
  return button;
}

function recordFixture(overrides: Partial<OrganizeRecordRead> = {}): OrganizeRecordRead {
  return {
    record_id: "job-42",
    display_index: "#42",
    job_id: 42,
    plan_id: "plan-42",
    short_plan_id: "plan-42",
    name: "Movie 42",
    source_path: "/media/incoming/Movie 42.mkv",
    target_path: "/media/organized/Movie 42/Movie 42.mkv",
    mode: "move",
    status: "completed",
    verification_status: "verified",
    metadata: {
      nfo: true,
      poster: true,
      fanart: false,
      thumb: false,
      backdrop: false,
      actors: true,
    },
    created_at: "2026-07-30T00:00:00Z",
    can_rollback: true,
    can_rerun: true,
    rerun_path: "/media/organized/Movie 42/Movie 42.mkv",
    source_paths: ["/media/incoming/Movie 42.mkv"],
    target_paths: ["/media/organized/Movie 42/Movie 42.mkv"],
    plan: null,
    ...overrides,
  };
}

function planFixture(): OperationPlan {
  return {
    plan_id: "plan-42",
    version: 1,
    database_id: 1,
    job_id: 42,
    mode: "move",
    destination_root: "/media/organized",
    target_directory: "/media/organized/Movie 42",
    source_snapshot: [],
    materialized_asset_cache_paths: [],
    steps: [
      {
        step_id: "plan-42:0001",
        operation: "move",
        category: "media",
        source_path: "/media/incoming/Movie 42.mkv",
        target_path: "/media/organized/Movie 42/Movie 42.mkv",
        temp_parent_path: "/media/organized/Movie 42",
        expected_size_bytes: 11,
        mtime_ns: null,
        sha256: null,
        sidecar: false,
        materialized_asset: false,
        generated_artifact: false,
        actor_output: false,
        destructive: true,
        allow_existing_generated_replacement: false,
        metadata: {},
      },
    ],
    conflicts: [],
    safety_warnings: [],
    created_at: "2026-07-30T00:00:00Z",
  };
}
