import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AppSettings } from "../api/types";
import { AutomaticMonitorsPage } from "./AutomaticMonitorsPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AutomaticMonitorsPage", () => {
  it("edits watch rules, auto-excludes nested destinations, and calls monitor APIs", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/settings",
        response: settingsFixture(),
      },
      {
        path: "/api/watch-rules",
        response: { rules: [watchRuleFixture()] },
      },
      {
        path: "/api/jobs?manual=false&limit=50",
        response: { jobs: [] },
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
    await waitFor(() =>
      expect(screen.getAllByLabelText(/目标目录/i)[0]).toHaveValue(
        "/media/default-organized",
      ),
    );
    expect(screen.getByRole("button", { name: "移动" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getAllByLabelText(/资源缺失处理/i)[0]).toHaveValue("lenient");
    expect(screen.getAllByLabelText(/文件夹模板/i)[0]).toHaveValue(
      "{studio}\n{xchina_id}",
    );
    expect(screen.getAllByLabelText(/文件名模板/i)[0]).toHaveValue(
      "{xchina_id} - {title}",
    );
    expect(screen.getByLabelText(/保存来源页面快照/i)).toBeChecked();
    for (const label of [
      "源目录",
      "目标目录",
      "递归",
      "轮询间隔",
      "稳定等待时间",
      "稳定检查次数",
      "置信度阈值",
      "资源缺失处理",
      "文件夹模板",
      "文件名模板",
      "包含模式",
      "排除模式",
      "已排除目标前缀",
    ]) {
      expect(screen.getAllByLabelText(new RegExp(label, "i"))[0]).toBeTruthy();
    }
    expect(screen.getAllByRole("button", { name: "选择目录" }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "添加前缀" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "实时" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "轮询" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "复制" })).toBeTruthy();

    fireEvent.change(screen.getAllByLabelText(/源目录/i)[0], {
      target: { value: "/media/incoming" },
    });
    fireEvent.change(screen.getAllByLabelText(/目标目录/i)[0], {
      target: { value: "/media/incoming/organized" },
    });

    expect(
      await screen.findByText(/目标目录位于被监控源目录内/i),
    ).toBeTruthy();
    await waitFor(() =>
      expect(screen.getAllByLabelText(/已排除目标前缀/i)[0]).toHaveValue(
        "/media/incoming/organized",
      ),
    );

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
    expect((createCall?.body as { organization_mode: string }).organization_mode).toBe("move");
    expect((createCall?.body as { folder_templates: string[] }).folder_templates).toEqual([
      "{studio}",
      "{xchina_id}",
    ]);
    expect((createCall?.body as { filename_template: string }).filename_template).toBe(
      "{xchina_id} - {title}",
    );
    expect((createCall?.body as { asset_policy: string }).asset_policy).toBe("lenient");
    expect(
      (createCall?.body as { metadata_options: Record<string, unknown> })
        .metadata_options.include_source_snapshot,
    ).toBe(true);

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

  it("loads compact progress logs for automatic queue jobs", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/settings",
        response: settingsFixture(),
      },
      {
        path: "/api/watch-rules",
        response: { rules: [watchRuleFixture()] },
      },
      {
        path: "/api/jobs?manual=false&limit=50",
        response: { jobs: [autoJobFixture()] },
      },
      {
        path: "/api/jobs/10/events",
        response: {
          events: [
            {
              id: 1,
              job_id: 10,
              from_state: null,
              to_state: "searching",
              payload: { api_key: "raw-secret" },
            },
            {
              id: 2,
              job_id: 10,
              from_state: "searching",
              to_state: "review_required",
              payload: {
                reason: "confidence_below_threshold",
                proxy: "http://user:pass@proxy.test:8080",
              },
            },
          ],
        },
      },
    ]);

    render(<AutomaticMonitorsPage />);

    fireEvent.click(await screen.findByRole("tab", { name: "任务队列" }));
    expect(await screen.findByText("Auto.Work.2026")).toBeTruthy();
    const progressLog = screen.getByLabelText("任务 10 进度日志");
    expect(progressLog).toHaveTextContent("搜索候选");
    expect(progressLog).toHaveTextContent("等待人工复核");
    expect(progressLog).toHaveTextContent("置信度低于阈值");
    expect(progressLog).not.toHaveTextContent("confidence_below_threshold");
    expect(progressLog).not.toHaveTextContent("raw-secret");
    expect(progressLog).not.toHaveTextContent("user:pass");

    await waitFor(() =>
      expect(calls.some((call) => call.url === "/api/jobs/10/events")).toBe(true),
    );
  });
});

function settingsFixture(): AppSettings {
  return {
    storage: { roots: ["/media"], env_roots: [] },
    xchina: {
      base_url: "https://www.xchina.co",
      flaresolverr_url: null,
      proxy_url: null,
      cache_dir: null,
    },
    emby: {
      enabled: false,
      server_url: null,
      api_key: null,
      path_mappings: [],
      upload_actor_portraits: true,
    },
    naming: {
      folder_templates: ["{studio}", "{title}"],
      filename_template: "{title}",
    },
    metadata_assets: {
      write_nfo: true,
      include_source_snapshot: false,
      asset_policy: "strict",
      max_asset_bytes: 10485760,
    },
    organization_defaults: {
      destination_directory: "/media/default-organized",
      organization_mode: "move",
      folder_templates: ["{studio}", "{xchina_id}"],
      filename_template: "{xchina_id} - {title}",
      asset_policy: "lenient",
      include_source_snapshot: true,
    },
    confidence_safety: {
      confidence_threshold: 92,
      refuse_destination_collisions: true,
      refuse_unresolved_multipart: true,
      cache_dir: null,
    },
    auth: {
      enabled: false,
      username: null,
    },
  };
}

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

function autoJobFixture() {
  return {
    id: 10,
    state: "review_required",
    media_identity: "Auto.Work.2026",
    rule_id: "rule-1",
    manual: false,
    attempts: 1,
    max_attempts: 3,
    next_run_at: null,
    last_error_code: null,
    payload: {},
    plan_id: null,
    selected_candidate: { title: "Candidate Title" },
    gate_reasons: ["confidence_below_threshold"],
    retryable: true,
    retry_emby_available: false,
  };
}
