import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutomaticMonitorsPage } from "./AutomaticMonitorsPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AutomaticMonitorsPage", () => {
  it("edits watch rules, auto-excludes nested destinations, and calls monitor APIs", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/watch-rules",
        response: { rules: [watchRuleFixture()] },
      },
      {
        path: "/api/jobs?state=review_required",
        response: { jobs: [] },
      },
      {
        path: "/api/storage-roots/browse?root_id=1",
        response: {
          root: { id: 1, path: "/media", source: "runtime", enabled: true },
          entries: [{ name: "incoming", path: "/media/incoming", is_dir: true }],
        },
      },
      {
        method: "POST",
        path: "/api/watch-rules",
        response: { ...watchRuleFixture(), rule_id: "rule-created" },
        status: 201,
      },
      {
        method: "PUT",
        path: "/api/watch-rules/rule-1",
        response: watchRuleFixture({ enabled: false }),
      },
      {
        method: "POST",
        path: "/api/watch-rules/rule-1/scan-now",
        response: { rule_id: "rule-1", enqueued_jobs: [10] },
      },
    ]);

    render(<AutomaticMonitorsPage />);

    expect(await screen.findByText("rule-1")).toBeTruthy();
    for (const label of [
      "Source directory",
      "Destination directory",
      "Recursive",
      "Polling interval seconds",
      "Stability duration seconds",
      "Stable check count",
      "Confidence threshold",
      "Asset policy",
      "Folder templates",
      "Filename template",
      "Include patterns",
      "Exclude patterns",
      "Excluded destination prefixes",
    ]) {
      expect(screen.getByLabelText(new RegExp(label, "i"))).toBeTruthy();
    }
    expect(screen.getByRole("button", { name: "Real-time" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Polling" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "copy" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/Source directory/i), {
      target: { value: "/media/incoming" },
    });
    fireEvent.change(screen.getByLabelText(/Destination directory/i), {
      target: { value: "/media/incoming/organized" },
    });

    expect(
      await screen.findByText(/Destination is inside the watched source/i),
    ).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByLabelText(/Excluded destination prefixes/i)).toHaveValue(
        "/media/incoming/organized",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Browse storage roots" }));
    expect(await screen.findByText("incoming")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Create watch rule" }));
    await waitFor(() =>
      expect(calls.some((call) => call.method === "POST" && call.url === "/api/watch-rules")).toBe(
        true,
      ),
    );
    const createCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/watch-rules",
    );
    expect(
      (createCall?.body as { excluded_destination_prefixes: string[] })
        .excluded_destination_prefixes,
    ).toContain("/media/incoming/organized");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Update watch rule" }));
    fireEvent.click(screen.getByRole("button", { name: "Scan now" }));

    await waitFor(() => {
      expect(calls.some((call) => call.method === "PUT" && call.url === "/api/watch-rules/rule-1")).toBe(
        true,
      );
      expect(calls.some((call) => call.url === "/api/watch-rules/rule-1/scan-now")).toBe(true);
    });
  });
});

function watchRuleFixture(patch: Partial<ReturnType<typeof baseWatchRule>> = {}) {
  return { ...baseWatchRule(), ...patch };
}

function baseWatchRule() {
  return {
    rule_id: "rule-1",
    source_directory: "/media/incoming",
    destination_directory: "/media/organized",
    recursive: true,
    realtime: true,
    polling_interval_seconds: 60,
    stability_seconds: 30,
    stable_check_count: 2,
    organization_mode: "copy",
    folder_templates: ["{studio}", "{title}"],
    filename_template: "{xchina_id} - {title}",
    asset_policy: "strict",
    emby_options: { notify: false },
    metadata_options: { write_nfo: true, poster: true, fanart: true },
    include_patterns: ["*.mkv"],
    exclude_patterns: ["*.tmp"],
    excluded_destination_prefixes: [],
    confidence_threshold: 92,
    enabled: true,
  };
}
