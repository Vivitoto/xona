import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { APP_VERSION_LABEL } from "./appVersion";
import { installFetchMock } from "./test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("App", () => {
  it("renders a heading named Xona", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
    ]);
    const { container } = render(<App />);

    expect(screen.getByRole("heading", { name: "Xona" })).toBeTruthy();
    expect(container.querySelector(".brand-mark img[src='/favicon.svg']")).toBeTruthy();
    expect(
      screen.getByLabelText(`Xona 版本 ${APP_VERSION_LABEL}`),
    ).toHaveTextContent(APP_VERSION_LABEL);
  });

  it("toggles theme mode and persists the selection", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
    ]);
    localStorage.setItem("xona-theme", "dark");
    render(<App />);

    const shell = screen.getByTestId("app-theme-root");
    expect(shell).toHaveAttribute("data-theme", "dark");

    fireEvent.click(screen.getByRole("button", { name: "浅色模式" }));

    expect(shell).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem("xona-theme")).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: "深色模式" }));

    expect(shell).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem("xona-theme")).toBe("dark");
  });

  it("exposes the v1.2 product navigation without retired primary entries", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
    ]);
    render(<App />);

    const navigation = screen.getByRole("navigation", { name: "主导航" });
    for (const name of [
      "仪表盘",
      "本地元数据生成",
      "XChina 元数据搜索",
      "整理记录",
      "日志",
      "设置",
    ]) {
      const navButton = within(navigation).getByRole("button", { name });
      expect(navButton).toBeTruthy();
      expect(navButton.querySelector("svg")).toBeTruthy();
    }

    for (const retiredName of [
      "手动整理",
      "未匹配视频",
      "自动监控",
      "复核队列",
      "任务记录",
      "历史/回滚",
      "演员库",
    ]) {
      expect(
        within(navigation).queryByRole("button", { name: retiredName }),
      ).not.toBeInTheDocument();
    }
  });

  it("renders the local metadata workflow from navigation", async () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/settings", response: settingsFixture() },
    ]);
    render(<App />);

    fireEvent.click(
      within(screen.getByRole("navigation", { name: "主导航" })).getByRole(
        "button",
        { name: "本地元数据生成" },
      ),
    );

    expect(
      await screen.findByRole("heading", { name: "本地元数据生成" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("视频路径")).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成 NFO 预览" })).toBeTruthy();
  });

  it("shows workflow shortcuts from the dashboard", async () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
    ]);
    render(<App />);

    const main = screen.getByRole("main");
    expect(await within(main).findByText("媒体工作台")).toBeTruthy();
    expect(
      await within(main).findByRole("button", { name: "本地元数据生成" }),
    ).toBeTruthy();
    expect(
      within(main).getByRole("button", { name: "XChina 元数据搜索" }),
    ).toBeTruthy();
    expect(within(main).getByText("流程示例")).toBeTruthy();
    for (const step of ["扫描", "草稿", "封面/NFO", "预览", "记录"]) {
      expect(within(main).getByText(step)).toBeTruthy();
    }
    for (const removedShortcut of ["未处理文件", "元数据复核", "任务与记录", "历史线索", "本地演员条目"]) {
      expect(within(main).queryByText(removedShortcut)).not.toBeInTheDocument();
    }
    expect(
      within(main).queryByRole("button", { name: "监控规则" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("复核")).not.toBeInTheDocument();
  });

  it("defaults image safety mode on and toggles independently from theme mode", async () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
    ]);
    localStorage.setItem("xona-theme", "dark");
    render(<App />);

    const shell = screen.getByTestId("app-theme-root");
    const safetyToggle = screen.getByRole("checkbox", {
      name: "安全模式：模糊图片",
    });
    expect(safetyToggle).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "浅色模式" }));
    expect(shell).toHaveAttribute("data-theme", "light");
    expect(safetyToggle).toBeChecked();

    fireEvent.click(safetyToggle);
    expect(safetyToggle).not.toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "深色模式" }));
    expect(shell).toHaveAttribute("data-theme", "dark");
    expect(safetyToggle).not.toBeChecked();
  });
});

function settingsFixture() {
  return {
    storage: { roots: ["/media"], env_roots: [] },
    xchina: {
      base_url: "https://xchina.co",
      flaresolverr_url: null,
      proxy_url: null,
      cache_dir: null,
      max_search_pages: 50,
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
      asset_policy: "lenient",
      max_asset_bytes: 10485760,
    },
    organization_defaults: {
      destination_directory: "/media/organized",
      organization_mode: "preview",
      folder_templates: ["{studio}", "{title}"],
      filename_template: "{title}",
      asset_policy: "lenient",
      include_source_snapshot: false,
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
