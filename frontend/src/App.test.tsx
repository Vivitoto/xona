import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { APP_VERSION_LABEL } from "./appVersion";
import { installFetchMock } from "./test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders a heading named Xona", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/actors", response: { actors: [] } },
    ]);
    render(<App />);

    expect(screen.getByRole("heading", { name: "Xona" })).toBeTruthy();
    expect(
      screen.getByLabelText(`Xona 版本 ${APP_VERSION_LABEL}`),
    ).toHaveTextContent("v1.1.3");
  });

  it("exposes every first-release navigation destination", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/actors", response: { actors: [] } },
    ]);
    render(<App />);

    for (const name of [
      "仪表盘",
      "手动整理",
      "未匹配视频",
      "自动监控",
      "复核队列",
      "任务中心",
      "演员库",
      "历史/回滚",
      "日志",
      "设置",
    ]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
  });

  it("renders the unmatched videos workflow from navigation", async () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/actors", response: { actors: [] } },
      { path: "/api/settings", response: settingsFixture() },
    ]);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "未匹配视频" }));

    expect(
      await screen.findByRole("heading", { name: "未匹配视频" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("视频路径")).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成 NFO 预览" })).toBeTruthy();
  });

  it("defaults image safety mode on and toggles candidate and actor image blur", async () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/actors", response: { actors: [actorFixture()] } },
      {
        method: "POST",
        path: "/api/manual/scan",
        response: {
          scanned_count: 1,
          jobs: [
            {
              job_id: 7,
              state: "discovered",
              media_identity: "sample-work",
              media_items: [
                {
                  path: "/media/incoming/Sample.Work.mkv",
                  group_key: "sample-work",
                  identity: "sample-work",
                  size_bytes: 4,
                  multipart_index: null,
                },
              ],
            },
          ],
        },
      },
      {
        method: "POST",
        path: "/api/manual/search",
        response: {
          job_id: 7,
          search_query_id: 11,
          query: "Sample Work",
          normalized_query: "Sample Work",
          candidates: [candidateFixture()],
        },
      },
    ]);
    render(<App />);

    const safetyToggle = screen.getByRole("checkbox", {
      name: "安全模式：模糊图片",
    });
    expect(safetyToggle).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "手动整理" }));
    fireEvent.change(screen.getByLabelText(/源目录/i), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "扫描源目录" }));
    await screen.findByText(/已扫描 1 个视频文件/);
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    const candidateImage = await screen.findByRole("img", {
      name: /Sample Work 候选图片/,
    });
    expect(candidateImage).toHaveClass("safety-image");
    expect(candidateImage).toHaveClass("is-blurred");
    expect(candidateImage).toHaveAttribute("data-image-safety", "blurred");

    fireEvent.click(safetyToggle);
    expect(safetyToggle).not.toBeChecked();
    expect(candidateImage).not.toHaveClass("is-blurred");
    expect(candidateImage).toHaveAttribute("data-image-safety", "visible");

    fireEvent.click(safetyToggle);
    expect(safetyToggle).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "演员库" }));

    const actorPortrait = await screen.findByRole("img", {
      name: /Actor One 头像/,
    });
    expect(actorPortrait).toHaveClass("safety-image");
    expect(actorPortrait).toHaveClass("is-blurred");
    expect(actorPortrait).toHaveAttribute("data-image-safety", "blurred");

    fireEvent.click(safetyToggle);
    expect(actorPortrait).not.toHaveClass("is-blurred");
    expect(actorPortrait).toHaveAttribute("data-image-safety", "visible");
  });
});

function candidateFixture() {
  return {
    candidate_id: 3,
    source: "xchina",
    source_candidate_id: "XC-001",
    title: "Sample Work",
    image_url: "https://images.example.test/poster.jpg",
    actors: ["Actor One"],
    studio: "Studio One",
    series: "Series One",
    release_date: "2026-01-02",
    url: "https://xchina.example.test/videos/xc-001.html",
    confidence_score: 96,
    score_breakdown: { title: 80, actors: 16 },
  };
}

function actorFixture() {
  return {
    id: 1,
    canonical_name: "Actor One",
    aliases: ["Alias One"],
    source: "xchina",
    source_id: "ACT-001",
    profile_url: "https://xchina.example.test/models/actor-one.html",
    portrait_source_url: "https://images.example.test/actor-one.jpg",
    portrait_cache_path: null,
    portrait_sha256: null,
    portrait_size_bytes: null,
    biography: null,
    profile_fields: {},
    associated_works: [],
    emby_person_id: null,
    linked_works: [],
  };
}

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
