import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AppSettings, AppSettingsUpdate } from "../api/types";
import { SettingsPage } from "./SettingsPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SettingsPage", () => {
  it("renders all settings sections and keeps FlareSolverr endpoint exact", async () => {
    installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { path: "/api/settings/cache-maintenance", response: cacheStatsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "XChina" })).toBeTruthy();

    expect(
      screen.getByLabelText(/精确 FlareSolverr 端点/i),
    ).toHaveValue("http://solver:8191/custom");
    expect(
      screen.getByText(/客户端不会追加 \/v1/i),
    ).toBeTruthy();
    expect(screen.getByLabelText(/代理 URL/i)).toHaveValue(
      "http://********:********@proxy.test:8080",
    );

    for (const [tab, heading] of [
      ["Emby", "Emby"],
      ["整理配置", "目录配置"],
      ["元数据/资源", "元数据/资源"],
      ["缓存维护", "缓存维护"],
      ["认证", "认证"],
    ]) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(screen.queryByRole("tab", { name: "置信度/安全" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "媒体目录" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "命名模板" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "整理默认值" })).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "整理配置" }));
    expect(screen.getByRole("heading", { name: "媒体目录" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "整理目标目录" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "命名模板" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "整理行为" })).toBeTruthy();
    expect(
      screen.getAllByRole("button", { name: "查看可用变量" }),
    ).toHaveLength(1);
  });

  it("omits unchanged secret placeholders and submits explicit new secrets", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await screen.findByLabelText(/Emby API key/i);
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const firstPut = calls.find((call) => call.method === "PUT");
    expect(JSON.stringify(firstPut?.body)).not.toContain("********");
    expect((firstPut?.body as AppSettings).emby).not.toHaveProperty("api_key");
    expect((firstPut?.body as AppSettings).xchina).not.toHaveProperty("proxy_url");

    fireEvent.change(screen.getByLabelText(/Emby API key/i), {
      target: { value: "new-emby-key" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "XChina" }));
    fireEvent.change(screen.getByLabelText(/代理 URL/i), {
      target: { value: "http://user:pass@proxy.test:8080" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.filter((call) => call.method === "PUT")).toHaveLength(2),
    );
    const secondPut = calls.filter((call) => call.method === "PUT")[1];
    expect((secondPut.body as AppSettings).emby.api_key).toBe("new-emby-key");
    expect((secondPut.body as AppSettings).xchina.proxy_url).toBe(
      "http://user:pass@proxy.test:8080",
    );
  });

  it("submits global organization defaults", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "整理配置" }));
    fireEvent.change(await screen.findByLabelText(/默认目标目录/i), {
      target: { value: "/media/defaults" },
    });
    fireEvent.change(screen.getByLabelText(/默认整理模式/i), {
      target: { value: "move" },
    });
    fireEvent.click(screen.getByLabelText(/默认保存来源页面快照/i));
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const put = calls.find((call) => call.method === "PUT");
    expect((put?.body as AppSettings).organization_defaults).toMatchObject({
      destination_directory: "/media/defaults",
      organization_mode: "move",
      include_source_snapshot: true,
    });
  });

  it("keeps one naming template and saves it to preview and organization defaults", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "整理配置" }));
    fireEvent.change(await screen.findByLabelText("文件夹模板"), {
      target: { value: "{studio}\n{series}\n{title}" },
    });
    fireEvent.change(screen.getByLabelText("文件名模板"), {
      target: { value: "{xchina_id} - {title} [{release_date}]" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const put = calls.find((call) => call.method === "PUT");
    expect((put?.body as AppSettings).naming).toMatchObject({
      folder_templates: ["{studio}", "{series}", "{title}"],
      filename_template: "{xchina_id} - {title} [{release_date}]",
    });
    expect((put?.body as AppSettings).organization_defaults).toMatchObject({
      folder_templates: ["{studio}", "{series}", "{title}"],
      filename_template: "{xchina_id} - {title} [{release_date}]",
    });
  });

  it("previews naming templates through the backend endpoint", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/settings/templates/preview",
        response: {
          folder_path: "Studio/Sample Work",
          filename: "XC-001 - Sample Work",
          validation_errors: [],
          warnings: [],
        },
      },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "整理配置" }));
    await screen.findByLabelText("文件名模板");
    fireEvent.click(screen.getByRole("button", { name: "预览命名模板" }));

    expect(await screen.findByText("XC-001 - Sample Work")).toBeTruthy();
    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/settings/templates/preview",
      ),
    ).toBe(true);
  });

  it("blocks saving when preflight validation finds template errors", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "整理配置" }));
    fireEvent.change(await screen.findByLabelText("文件名模板"), {
      target: { value: "{unknown_variable}" },
    });

    expect(await screen.findByText(/命名模板包含未知变量/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
    expect(calls.filter((call) => call.method === "PUT")).toHaveLength(0);
  });

  it("tests XChina with the current unsaved form values", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/settings/xchina/test",
        response: { ok: true, candidate_count: 2, diagnostics: {} },
      },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.change(screen.getByLabelText("XChina 基础 URL"), {
      target: { value: "https://mirror.xchina.test" },
    });
    fireEvent.change(screen.getByLabelText("XChina 测试查询"), {
      target: { value: "txvlog" },
    });
    fireEvent.change(screen.getByLabelText("搜索页数安全上限"), {
      target: { value: "7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "测试 XChina" }));

    await screen.findByText(/candidate_count/);
    const testCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/settings/xchina/test",
    );
    expect(testCall?.body).toMatchObject({
      query: "txvlog",
      base_url: "https://mirror.xchina.test",
      flaresolverr_url: "http://solver:8191/custom",
      max_search_pages: 7,
    });
    expect(testCall?.body).not.toHaveProperty("proxy_url");
  });

  it("keeps confidence safety hidden from preflight and save payload", async () => {
    const settingsWithLegacyConfidence = settingsFixture();
    settingsWithLegacyConfidence.confidence_safety = {
      ...settingsWithLegacyConfidence.confidence_safety,
      confidence_threshold: 150,
    };
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsWithLegacyConfidence },
      { method: "PUT", path: "/api/settings", response: settingsWithLegacyConfidence },
    ]);

    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "XChina" });
    expect(screen.queryByRole("tab", { name: "置信度/安全" })).toBeNull();
    expect(screen.queryByText(/置信度/)).toBeNull();

    fireEvent.change(screen.getByLabelText("XChina 基础 URL"), {
      target: { value: "https://mirror.xchina.test" },
    });

    expect(await screen.findByText("XChina 基础 URL 将更新")).toBeTruthy();
    expect(screen.queryByText(/置信度/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const put = calls.find((call) => call.method === "PUT");
    expect(put?.body).not.toHaveProperty("confidence_safety");
    expect((put?.body as AppSettingsUpdate).xchina).toMatchObject({
      base_url: "https://mirror.xchina.test",
    });
  });

  it("loads cache maintenance stats and cleans selected safe cache areas", async () => {
    let cleaned = false;
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        path: "/api/settings/cache-maintenance",
        response: () => (cleaned ? cacheStatsFixture({ empty: true }) : cacheStatsFixture()),
      },
      {
        method: "POST",
        path: "/api/settings/cache-maintenance/cleanup",
        response: () => {
          cleaned = true;
          return {
            results: [],
            deleted_files: 3,
            deleted_bytes: 3072,
            warnings: [],
          };
        },
      },
    ]);

    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "缓存维护" }));

    expect(await screen.findByText("本地元数据缓存")).toBeTruthy();
    expect(screen.getAllByText("3.00 KB").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText("选择本地元数据缓存"));
    fireEvent.click(screen.getByRole("button", { name: "清理所选缓存" }));

    await screen.findByText(/缓存清理完成/);
    expect(confirmSpy).toHaveBeenCalled();
    const cleanupCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/settings/cache-maintenance/cleanup",
    );
    expect(cleanupCall?.body).toEqual({ area_keys: ["local_metadata"] });
  });
});

function cacheStatsFixture({ empty = false }: { empty?: boolean } = {}) {
  return {
    areas: [
      {
        key: "local_metadata",
        label: "本地元数据缓存",
        path: "/config/cache/local_metadata",
        exists: !empty,
        cleanup_supported: true,
        file_count: empty ? 0 : 3,
        size_bytes: empty ? 0 : 3072,
        warnings: [],
      },
      {
        key: "asset_cache",
        label: "元数据资源缓存",
        path: "/config/asset-cache",
        exists: false,
        cleanup_supported: true,
        file_count: 0,
        size_bytes: 0,
        warnings: ["cache_dir_missing:/config/asset-cache"],
      },
    ],
    total_file_count: empty ? 0 : 3,
    total_size_bytes: empty ? 0 : 3072,
    warnings: [],
  };
}

function settingsFixture(): AppSettings {
  return {
    storage: { roots: ["/media"], env_roots: [] },
    xchina: {
      base_url: "https://www.xchina.co",
      flaresolverr_url: "http://solver:8191/custom",
      proxy_url: "http://********:********@proxy.test:8080",
      cache_dir: "/config/cache/xchina",
    },
    emby: {
      enabled: true,
      server_url: "http://emby.test",
      api_key: "********",
      path_mappings: [{ container_root: "/media", emby_root: "/visible" }],
      upload_actor_portraits: true,
    },
    naming: {
      folder_templates: ["{studio}", "{title}"],
      filename_template: "{xchina_id} - {title}",
    },
    metadata_assets: {
      write_nfo: true,
      include_source_snapshot: false,
      asset_policy: "strict",
      max_asset_bytes: 10485760,
    },
    organization_defaults: {
      destination_directory: "/media/organized",
      organization_mode: "hardlink",
      folder_templates: ["{studio}", "{xchina_id} - {title}"],
      filename_template: "{xchina_id} - {title}",
      asset_policy: "strict",
      include_source_snapshot: false,
    },
    confidence_safety: {
      confidence_threshold: 92,
      refuse_destination_collisions: true,
      refuse_unresolved_multipart: true,
      cache_dir: "/config/cache/safety",
    },
    auth: {
      enabled: false,
      username: "vito",
    },
  };
}
