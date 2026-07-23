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
      "源目录",
      "目标目录",
      "递归",
      "轮询间隔",
      "稳定等待时间",
      "稳定检查次数",
      "置信度阈值",
      "资源策略",
      "文件夹模板",
      "文件名模板",
      "包含模式",
      "排除模式",
      "已排除目标前缀",
    ]) {
      expect(screen.getByLabelText(new RegExp(label, "i"))).toBeTruthy();
    }
    expect(screen.getByRole("button", { name: "实时" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "轮询" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "复制" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/源目录/i), {
      target: { value: "/media/incoming" },
    });
    fireEvent.change(screen.getByLabelText(/目标目录/i), {
      target: { value: "/media/incoming/organized" },
    });

    expect(
      await screen.findByText(/目标目录位于被监控源目录内/i),
    ).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByLabelText(/已排除目标前缀/i)).toHaveValue(
        "/media/incoming/organized",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "浏览存储根" }));
    expect(await screen.findByText("incoming")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "创建监控规则" }));
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

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByRole("button", { name: "更新监控规则" }));
    fireEvent.click(screen.getByRole("button", { name: "立即扫描" }));

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
