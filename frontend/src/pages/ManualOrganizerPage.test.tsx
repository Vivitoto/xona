import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AppSettings } from "../api/types";
import { ManualOrganizerPage } from "./ManualOrganizerPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ManualOrganizerPage", () => {
  it("supports browse, scan, search, select, and starts organization through one action", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/storage-roots",
        response: {
          roots: [{ id: 1, path: "/media", source: "runtime", enabled: true }],
        },
      },
      {
        path: "/api/storage-roots/browse?root_id=1&path=",
        response: {
          root: { id: 1, path: "/media", source: "runtime", enabled: true },
          entries: [{ name: "incoming", path: "/media/incoming", is_dir: true }],
        },
      },
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
          candidates: [
            {
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
            },
          ],
        },
      },
      {
        method: "POST",
        path: "/api/manual/jobs/7/select-candidate",
        response: {
          job_id: 7,
          accepted: true,
          reasons: [],
          selected_candidate: {
            candidate_id: 3,
            source: "xchina",
            source_candidate_id: "XC-001",
            title: "Sample Work",
            image_url: "https://images.example.test/poster-detail.jpg",
            actors: ["Actor One"],
            studio: "Studio One",
            series: "Series One",
            release_date: "2026-01-02",
            url: "https://xchina.example.test/videos/xc-001.html",
            confidence_score: 96,
            score_breakdown: { title: 80, actors: 16 },
          },
          metadata_record_id: 5,
          metadata: {
            source: "xchina",
            xchina_id: "XC-001",
            source_url: "https://xchina.example.test/videos/xc-001.html",
            title: "Sample Work",
            original_title: "Original Sample Work",
            plot: "A short plot for checking the selected detail card.",
            release_date: "2026-01-02",
            runtime_minutes: 88,
            studio: "Studio One",
            series: "Series One",
            director: "Director One",
            actors: [{ name: "Actor One" }, { name: "Actor Two" }],
            genres: ["Drama"],
            tags: ["Featured"],
            assets: { poster_url: "https://images.example.test/poster-detail.jpg" },
          },
        },
      },
      {
        method: "POST",
        path: "/api/manual/jobs/7/organize",
        response: {
          plan_id: "plan-1",
          job_id: 7,
          state: "completed",
        },
      },
    ]);

    render(<ManualOrganizerPage />);

    expect(screen.getByPlaceholderText("/media/incoming")).toBeTruthy();
    expect(screen.getByRole("button", { name: "扫描源目录" })).toBeDisabled();
    expect(screen.getByText(/还没有视频文件/i)).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("/media/incoming"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "扫描源目录" }));
    expect(await screen.findByText("已扫描 1 个视频文件")).toBeTruthy();
    expect(screen.getByRole("button", { name: "用文件名搜索" })).toBeEnabled();

    fireEvent.change(screen.getByLabelText(/搜索关键词/i), {
      target: { value: "Sample Work" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    expect(await screen.findByRole("heading", { name: "Sample Work" })).toBeTruthy();
    expect(screen.getByAltText("Sample Work 候选图片")).toHaveAttribute(
      "src",
      "/api/manual/image-proxy?url=https%3A%2F%2Fimages.example.test%2Fposter.jpg",
    );
    expect(screen.getByText("ID XC-001")).toBeTruthy();
    expect(screen.getByText("Actor One")).toBeTruthy();
    expect(screen.getByText("title: 80")).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回修改搜索" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "返回修改搜索" }));
    expect(screen.getByLabelText(/搜索关键词/i)).toHaveValue("Sample Work");

    fireEvent.click(screen.getByRole("button", { name: "选择候选项" }));
    const selectedDetail = await screen.findByLabelText("已选候选详情");
    expect(within(selectedDetail).getByAltText("Sample Work 已选详情图片")).toHaveAttribute(
      "src",
      "/api/manual/image-proxy?url=https%3A%2F%2Fimages.example.test%2Fposter-detail.jpg",
    );
    expect(within(selectedDetail).getByText("原标题：Original Sample Work")).toBeTruthy();
    expect(within(selectedDetail).getByText("Actor One, Actor Two")).toBeTruthy();
    expect(within(selectedDetail).getByText("Director One")).toBeTruthy();
    expect(within(selectedDetail).getByText("88 分钟")).toBeTruthy();
    expect(within(selectedDetail).getByText("Drama")).toBeTruthy();
    expect(within(selectedDetail).getByText("Featured")).toBeTruthy();
    expect(
      within(selectedDetail).getByText("A short plot for checking the selected detail card."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("复核原因")).toBeNull();
    expect(screen.queryByRole("button", { name: "预览整理计划" })).toBeNull();
    expect(screen.queryByRole("button", { name: "执行已批准预览" })).toBeNull();
    expect(screen.getByRole("button", { name: "开始整理" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/目标目录/i), {
      target: { value: "/media/organized" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始整理" }));
    expect((await screen.findAllByText(/计划 plan-1：整理完成/)).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("操作计划")).toBeNull();
    const progressLog = screen.getByLabelText("整理进度日志");
    expect(within(progressLog).getByText("规划整理")).toBeTruthy();
    expect(within(progressLog).getByText("安全计划完成")).toBeTruthy();
    expect(within(progressLog).getByText("执行整理")).toBeTruthy();
    expect(within(progressLog).getByText("整理完成")).toBeTruthy();

    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/manual/jobs/7/organize",
      ),
    ).toBe(true);
    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/manual/jobs/7/preview",
      ),
    ).toBe(false);
    const organizeCall = calls.find((call) =>
      call.url.endsWith("/api/manual/jobs/7/organize"),
    );
    expect((organizeCall?.body as { mode: string }).mode).toBe("copy");
  });

  it("shows review reasons and blocks organization until candidate checks pass", async () => {
    const { calls } = installFetchMock([
      {
        method: "POST",
        path: "/api/manual/scan",
        response: {
          scanned_count: 1,
          jobs: [
            manualJobFixture({
              job_id: 8,
              media_identity: "needs-review",
              path: "/media/incoming/Needs.Review.mkv",
            }),
          ],
        },
      },
      {
        method: "POST",
        path: "/api/manual/search",
        response: {
          job_id: 8,
          search_query_id: 12,
          query: "Needs Review",
          normalized_query: "Needs Review",
          candidates: [
            {
              candidate_id: 4,
              source: "xchina",
              source_candidate_id: "XC-REVIEW",
              title: "Needs Review",
              image_url: null,
              actors: [],
              studio: null,
              series: null,
              release_date: null,
              url: "https://xchina.example.test/videos/needs-review.html",
              confidence_score: 80,
              score_breakdown: { title: 80 },
            },
          ],
        },
      },
      {
        method: "POST",
        path: "/api/manual/jobs/8/select-candidate",
        response: {
          job_id: 8,
          accepted: false,
          reasons: ["unresolved_multipart", "unsafe_path"],
          selected_candidate: {
            candidate_id: 4,
            source: "xchina",
            source_candidate_id: "XC-REVIEW",
            title: "Needs Review",
            image_url: null,
            actors: [],
            studio: null,
            series: null,
            release_date: null,
            url: "https://xchina.example.test/videos/needs-review.html",
            confidence_score: 80,
            score_breakdown: { title: 80 },
          },
          metadata_record_id: null,
          metadata: {
            title: "Needs Review",
            original_title: null,
            actors: [],
            assets: {},
          },
        },
      },
    ]);

    render(<ManualOrganizerPage />);

    fireEvent.change(screen.getByPlaceholderText("/media/incoming"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "扫描源目录" }));
    expect(await screen.findByText("已扫描 1 个视频文件")).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/搜索关键词/i), {
      target: { value: "Needs Review" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    expect(await screen.findByRole("heading", { name: "Needs Review" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "选择候选项" }));
    const reviewReasons = await screen.findByLabelText("复核原因");
    expect(within(reviewReasons).getByText("多段视频需确认")).toBeTruthy();
    expect(within(reviewReasons).getByText("路径不安全")).toBeTruthy();
    expect(screen.getByRole("button", { name: "开始整理" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/目标目录/i), {
      target: { value: "/media/organized" },
    });
    expect(screen.getByRole("button", { name: "开始整理" })).toBeDisabled();
    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/manual/jobs/8/organize",
      ),
    ).toBe(false);
  });

  it("keeps custom search text while editing instead of replacing it with media identity", async () => {
    installFetchMock([
      {
        method: "POST",
        path: "/api/manual/scan",
        response: {
          scanned_count: 1,
          jobs: [
            manualJobFixture({
              job_id: 9,
              media_identity: "inode:64768:366837790",
              path: "/media/incoming/ABP-123.mkv",
            }),
          ],
        },
      },
    ]);

    render(<ManualOrganizerPage />);

    fireEvent.change(screen.getByPlaceholderText("/media/incoming"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "扫描源目录" }));
    expect(await screen.findByText("已扫描 1 个视频文件")).toBeTruthy();

    const searchInput = screen.getByLabelText(/搜索关键词/i);
    expect(searchInput).toHaveValue("ABP 123");

    fireEvent.change(searchInput, { target: { value: "ABP" } });
    expect(searchInput).toHaveValue("ABP");

    fireEvent.change(searchInput, { target: { value: "AB" } });
    expect(searchInput).toHaveValue("AB");
    expect(searchInput).not.toHaveValue("inode:64768:366837790");
  });

  it("paginates media files and keeps full paths out of the left file list", async () => {
    installFetchMock([
      {
        method: "POST",
        path: "/api/manual/scan",
        response: {
          scanned_count: 12,
          jobs: Array.from({ length: 12 }, (_, index) =>
            manualJobFixture({
              job_id: index + 1,
              media_identity: `identity-${index + 1}`,
              path: `/media/incoming/Folder ${index + 1}/Movie ${index + 1}.mkv`,
            }),
          ),
        },
      },
    ]);

    render(<ManualOrganizerPage />);

    fireEvent.change(screen.getByPlaceholderText("/media/incoming"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "扫描源目录" }));
    expect(await screen.findByText("已扫描 12 个视频文件")).toBeTruthy();

    const fileList = screen.getByLabelText("扫描到的视频文件");
    expect(within(fileList).getByText("共 12 个视频，显示第 1-10 个")).toBeTruthy();
    expect(within(fileList).getByText("Movie 1.mkv")).toBeTruthy();
    expect(within(fileList).queryByText("/media/incoming/Folder 1/Movie 1.mkv")).toBeNull();
    expect(within(fileList).queryByText("Movie 11.mkv")).toBeNull();

    fireEvent.click(within(fileList).getByRole("button", { name: "下一页" }));
    expect(within(fileList).getByText("共 12 个视频，显示第 11-12 个")).toBeTruthy();
    expect(within(fileList).getByText("Movie 11.mkv")).toBeTruthy();
    expect(within(fileList).queryByText("Movie 1.mkv")).toBeNull();

    fireEvent.change(within(fileList).getByLabelText("每页显示视频数量"), {
      target: { value: "5" },
    });
    expect(within(fileList).getByText("共 12 个视频，显示第 1-5 个")).toBeTruthy();
  });

  it("prefills organization configuration from organization defaults", async () => {
    installFetchMock([
      {
        path: "/api/settings",
        response: manualSettingsFixture(),
      },
    ]);

    render(<ManualOrganizerPage />);

    expect(await screen.findByLabelText(/目标目录/i)).toHaveValue("/media/default");
    expect(screen.getByLabelText(/整理模式/i)).toHaveValue("hardlink");
    expect(screen.getByLabelText(/资源缺失处理/i)).toHaveValue("strict");
    expect(screen.getByLabelText(/包含源快照/i)).toBeChecked();
    expect(screen.getByLabelText(/文件夹模板/i)).toHaveValue(
      "{studio}\n{xchina_id} - {title}",
    );
    expect(screen.getByLabelText(/文件名模板/i)).toHaveValue(
      "{xchina_id} - {title}",
    );
  });

  it("does not overwrite edited organization fields when defaults load late", async () => {
    let resolveSettings: (settings: AppSettings) => void = () => undefined;
    const settingsPromise = new Promise<AppSettings>((resolve) => {
      resolveSettings = resolve;
    });
    installFetchMock([
      {
        path: "/api/settings",
        response: async () => settingsPromise,
      },
    ]);

    render(<ManualOrganizerPage />);

    fireEvent.change(screen.getByLabelText(/目标目录/i), {
      target: { value: "/media/user-choice" },
    });
    resolveSettings(manualSettingsFixture());

    await waitFor(() =>
      expect(screen.getByLabelText(/目标目录/i)).toHaveValue("/media/user-choice"),
    );
  });
});

function manualJobFixture({
  job_id,
  media_identity,
  path,
}: {
  job_id: number;
  media_identity: string;
  path: string;
}) {
  return {
    job_id,
    state: "discovered",
    media_identity,
    media_items: [
      {
        path,
        group_key: media_identity,
        identity: media_identity,
        size_bytes: 4,
        multipart_index: null,
      },
    ],
  };
}

function manualSettingsFixture(): AppSettings {
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
      asset_policy: "lenient",
      max_asset_bytes: 10485760,
    },
    organization_defaults: {
      destination_directory: "/media/default",
      organization_mode: "hardlink",
      folder_templates: ["{studio}", "{xchina_id} - {title}"],
      filename_template: "{xchina_id} - {title}",
      asset_policy: "strict",
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
