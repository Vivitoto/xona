import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AppSettings } from "../api/types";
import { installFetchMock } from "../test/mockFetch";
import { UnmatchedVideosPage } from "./UnmatchedVideosPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UnmatchedVideosPage", () => {
  it("exposes organize filename separately from metadata title", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/analyze",
        response: {
          video_path: "/media/incoming/Raw.Local.Work.mp4",
          cleaned_title: "Cleaned Local Work",
          default_organize_filename: "Cleaned Local Work",
          default_plot: "Local metadata generated for Raw.Local.Work.mp4.",
          default_tags: ["local-generated", "unmatched"],
          technical: {
            path: "/media/incoming/Raw.Local.Work.mp4",
            size_bytes: 4,
            duration_seconds: 120,
            width: 1920,
            height: 1080,
            video_codec: "h264",
            audio_codec: "aac",
            format_name: "mp4",
            bit_rate: 5000000,
            fps: 29.97,
          },
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/preview-plan",
        response: {
          plan_id: "plan-local",
          metadata: { title: "Metadata Title" },
          materialized_assets: [],
          nfo_xml: "<movie><title>Metadata Title</title></movie>",
          plan: operationPlanFixture(),
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    expect(screen.getByLabelText("整理文件名")).toBeTruthy();
    expect(screen.getByText(/标题写入 NFO 元数据/)).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );

    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Raw.Local.Work.mp4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析" }));

    const organizeInput = screen.getByLabelText("整理文件名") as HTMLInputElement;
    await waitFor(() => expect(organizeInput).toHaveValue("Cleaned Local Work"));

    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "Metadata Title" },
    });
    fireEvent.change(organizeInput, {
      target: { value: "Custom Output Name" },
    });
    fireEvent.change(screen.getByLabelText("额外截图数量"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成整理预览" }));

    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.url === "/api/local-metadata/preview-plan",
        ),
      ).toBe(true),
    );
    const previewCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/local-metadata/preview-plan",
    );
    expect(previewCall?.body).toMatchObject({
      metadata: {
        title: "Metadata Title",
        organize_filename: "Custom Output Name",
      },
      selected_frame_ids: [],
      extra_backdrop_count: 2,
    });
  });

  it("keeps manual video path input while adding a single video path picker", async () => {
    installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        path: "/api/storage-roots",
        response: {
          roots: [
            {
              id: 1,
              path: "/media",
              source: "user",
              enabled: true,
            },
          ],
        },
      },
      {
        path: "/api/storage-roots/browse?root_id=1&path=",
        response: {
          root: {
            id: 1,
            path: "/media",
            source: "user",
            enabled: true,
          },
          entries: [
            {
              name: "incoming",
              path: "/media/incoming",
              is_dir: true,
            },
            {
              name: "Picked.Scene.mp4",
              path: "/media/Picked.Scene.mp4",
              is_dir: false,
            },
          ],
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    const pathInput = screen.getByLabelText("视频路径");
    fireEvent.change(pathInput, {
      target: { value: "/manual/Typed.Scene.mp4" },
    });
    expect(pathInput).toHaveValue("/manual/Typed.Scene.mp4");

    fireEvent.click(screen.getByRole("button", { name: "选择视频" }));
    const dialog = await screen.findByRole("dialog", { name: "选择视频文件" });
    fireEvent.click(
      await within(dialog).findByRole("button", {
        name: "选择视频文件 Picked.Scene.mp4",
      }),
    );

    expect(pathInput).toHaveValue("/media/Picked.Scene.mp4");
    expect(screen.queryByRole("dialog", { name: "选择视频文件" })).toBeNull();
  });

  it("creates loadable page-local batch drafts and previews the loaded draft", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/scan",
        response: {
          scanned_count: 2,
          videos: [
            scannedVideoFixture({
              path: "/media/incoming/Alpha.Scene.mp4",
              filename: "Alpha.Scene.mp4",
              cleaned_title: "Alpha Scene",
              default_organize_filename: "Alpha Scene",
              size_bytes: 2048,
            }),
            scannedVideoFixture({
              path: "/media/incoming/Beta.Scene.mkv",
              filename: "Beta.Scene.mkv",
              cleaned_title: "Beta Scene",
              default_organize_filename: "Beta Custom",
              size_bytes: 4096,
            }),
          ],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/preview-plan",
        response: {
          plan_id: "plan-batch",
          metadata: { title: "Edited Beta Scene" },
          materialized_assets: [],
          nfo_xml: "<movie><title>Edited Beta Scene</title></movie>",
          plan: operationPlanFixture(),
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    const singleTab = screen.getByRole("tab", { name: "单个整理" });
    const batchTab = screen.getByRole("tab", { name: "批量整理" });
    expect(singleTab).toHaveAttribute("aria-selected", "true");
    expect(batchTab).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("heading", { name: "单个视频" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "批量整理列表" })).toBeNull();
    expect(
      screen.getByRole("status", { name: "单个整理预览状态" }),
    ).toHaveTextContent("单个整理预览状态");

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );

    fireEvent.click(batchTab);
    expect(batchTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "批量整理列表" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "单个视频" })).toBeNull();
    expect(screen.getByRole("heading", { name: "整理预览" })).toBeTruthy();
    expect(
      screen.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("等待扫描目录");
    expect(
      screen.getByRole("status", { name: "批量整理预览状态" }),
    ).toHaveTextContent("批量整理预览状态");

    const batchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(batchSection).toBeTruthy();
    const batch = within(batchSection as HTMLElement);

    fireEvent.change(batch.getByLabelText("目录路径"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(batch.getByRole("button", { name: "扫描目录" }));

    await waitFor(() => expect(batch.getByText("Alpha.Scene.mp4")).toBeTruthy());
    expect(batch.getByText("Beta.Scene.mkv")).toBeTruthy();
    const scanCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/local-metadata/scan",
    );
    expect(scanCall?.body).toMatchObject({
      directory: "/media/incoming",
      recursive: true,
      ignore_patterns: [],
    });

    fireEvent.change(batch.getByLabelText("标题前缀"), {
      target: { value: "[Batch] " },
    });
    fireEvent.change(batch.getByLabelText("标题后缀"), {
      target: { value: " - Draft" },
    });
    fireEvent.change(batch.getByLabelText("整理文件名前缀"), {
      target: { value: "OF_" },
    });
    fireEvent.change(batch.getByLabelText("整理文件名后缀"), {
      target: { value: "_OUT" },
    });
    fireEvent.change(batch.getByLabelText("制作方"), {
      target: { value: "Batch Studio" },
    });
    fireEvent.change(batch.getByLabelText("系列"), {
      target: { value: "Batch Series" },
    });
    fireEvent.change(batch.getByLabelText("标签"), {
      target: { value: "batch-tag\nlocal-generated" },
    });
    fireEvent.change(batch.getByLabelText("类型"), {
      target: { value: "Drama\nLocal" },
    });
    fireEvent.change(batch.getByLabelText("简介"), {
      target: { value: "Batch plot text." },
    });

    fireEvent.click(batch.getByRole("button", { name: "为已选视频生成整理信息" }));

    await waitFor(() => expect(batch.getByText("已生成的整理信息")).toBeTruthy());
    expect(
      batch.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("已生成 2 个视频整理信息");
    expect(batch.getByText("[Batch] Alpha Scene - Draft")).toBeTruthy();
    expect(batch.getByText("OF_Alpha Scene_OUT")).toBeTruthy();
    expect(batch.getByText("[Batch] Beta Scene - Draft")).toBeTruthy();
    expect(batch.getByText("OF_Beta Custom_OUT")).toBeTruthy();

    fireEvent.click(
      batch.getByRole("button", { name: "载入整理信息 Beta.Scene.mkv" }),
    );

    fireEvent.click(singleTab);
    const editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    const editor = within(editorSection as HTMLElement);

    await waitFor(() =>
      expect(editor.getByLabelText("标题")).toHaveValue("[Batch] Beta Scene - Draft"),
    );
    expect(editor.getByLabelText("整理文件名")).toHaveValue("OF_Beta Custom_OUT");
    expect(editor.getByLabelText("制作方")).toHaveValue("Batch Studio");
    expect(editor.getByLabelText("系列")).toHaveValue("Batch Series");
    expect(editor.getByLabelText("简介")).toHaveValue("Batch plot text.");
    expect(editor.getByLabelText("标签")).toHaveValue("batch-tag\nlocal-generated");
    expect(editor.getByLabelText("类型")).toHaveValue("Drama\nLocal");

    fireEvent.change(editor.getByLabelText("标题"), {
      target: { value: "Edited Beta Scene" },
    });

    fireEvent.click(batchTab);
    const updatedBatchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(updatedBatchSection).toBeTruthy();
    const updatedBatch = within(updatedBatchSection as HTMLElement);
    fireEvent.click(
      updatedBatch.getByRole("button", { name: "保存当前草稿到 Beta.Scene.mkv" }),
    );
    expect(updatedBatch.getByText("Edited Beta Scene")).toBeTruthy();
    expect(updatedBatch.getByText("已更新")).toBeTruthy();

    const batchPreviewSection = screen
      .getByRole("heading", { name: "整理预览" })
      .closest("section");
    expect(batchPreviewSection).toBeTruthy();
    const batchPreview = within(batchPreviewSection as HTMLElement);
    expect(
      batchPreview.getByRole("status", { name: "批量整理预览状态" }),
    ).toHaveTextContent("可生成整理预览");

    fireEvent.click(batchPreview.getByRole("button", { name: "生成整理预览" }));

    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.url === "/api/local-metadata/preview-plan",
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(
        batchPreview.getByRole("status", { name: "批量整理预览状态" }),
      ).toHaveTextContent("整理预览已生成"),
    );
    const previewCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/local-metadata/preview-plan",
    );
    expect(previewCall?.body).toMatchObject({
      metadata: {
        video_path: "/media/incoming/Beta.Scene.mkv",
        title: "Edited Beta Scene",
        organize_filename: "OF_Beta Custom_OUT",
        studio: "Batch Studio",
        series: "Batch Series",
        plot: "Batch plot text.",
        tags: ["batch-tag", "local-generated"],
        genres: ["Drama", "Local"],
      },
      destination_root: "/media/organized",
      mode: "copy",
      folder_templates: ["{studio}", "{title}"],
      filename_template: "{title}",
    });
  });

  it("requires selected frames for cover preview and clears stale cover and plan previews", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/analyze",
        response: {
          video_path: "/media/incoming/Frame.Source.mp4",
          cleaned_title: "Frame Source",
          default_organize_filename: "Frame Source",
          default_plot: "Local metadata generated for Frame.Source.mp4.",
          default_tags: ["local-generated", "unmatched"],
          technical: {
            path: "/media/incoming/Frame.Source.mp4",
            size_bytes: 4,
            duration_seconds: 120,
            width: 1920,
            height: 1080,
            video_codec: "h264",
            audio_codec: "aac",
            format_name: "mp4",
            bit_rate: 5000000,
            fps: 29.97,
          },
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/frames",
        response: {
          video_path: "/media/incoming/Frame.Source.mp4",
          frames: [
            cachedAssetFixture({
              id: "frames/frame-a.jpg",
              url: "/api/local-metadata/cache/frames/frame-a.jpg",
              time_seconds: 12,
            }),
            cachedAssetFixture({
              id: "frames/frame-b.jpg",
              url: "/api/local-metadata/cache/frames/frame-b.jpg",
              time_seconds: 60,
            }),
          ],
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/cover-preview",
        response: {
          poster: cachedAssetFixture({
            id: "covers/poster.jpg",
            kind: "poster",
            url: "/api/local-metadata/cache/covers/poster.jpg",
            width: 900,
            height: 1350,
          }),
          fanart: cachedAssetFixture({
            id: "covers/fanart.jpg",
            kind: "fanart",
            url: "/api/local-metadata/cache/covers/fanart.jpg",
            width: 1600,
            height: 900,
          }),
          template: "simple_poster",
          title_font_id: "source_han_sans",
          selected_frame_ids: ["frames/frame-a.jpg"],
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/preview-plan",
        response: {
          plan_id: "plan-local",
          metadata: { title: "Frame Source" },
          materialized_assets: [],
          nfo_xml: "<movie><title>Frame Source</title></movie>",
          plan: operationPlanFixture(),
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );
    expect(screen.getByText("分析文件或扫描目录")).toBeTruthy();
    expect(screen.getByText(/封面预览需要先生成截图/)).toBeTruthy();
    expect(screen.getByText(/优先使用已选截图/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Frame.Source.mp4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析" }));
    await waitFor(() =>
      expect(screen.getByLabelText("标题")).toHaveValue("Frame Source"),
    );
    expect(screen.getByLabelText("封面文字")).toHaveValue("Frame Source");
    expect(screen.getByLabelText("封面字体")).toHaveValue("source_han_sans");
    expect(screen.getByLabelText("文字倾斜角度")).toHaveValue(-8);
    expect(screen.getByLabelText("文字横向位置")).toBeTruthy();
    expect(screen.getByLabelText("文字纵向位置")).toBeTruthy();

    const coverButton = screen.getByRole("button", { name: "生成封面预览" });
    expect(coverButton).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "生成截图" }));

    const firstFrame = await screen.findByRole("button", { name: /截图 0:12/ });
    const secondFrame = screen.getByRole("button", { name: /截图 1:00/ });
    expect(screen.getByText("已选择 2 张截图用于封面和背景图。")).toBeTruthy();
    expect(coverButton).not.toBeDisabled();

    fireEvent.click(firstFrame);
    fireEvent.click(secondFrame);
    expect(screen.getByText("已选择 0 张截图用于封面和背景图。")).toBeTruthy();
    expect(coverButton).toBeDisabled();

    fireEvent.click(firstFrame);
    expect(screen.getByText("已选择 1 张截图用于封面和背景图。")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("封面文字"), {
      target: { value: "Poster Manual\nFrame Source" },
    });
    fireEvent.change(screen.getByLabelText("文字倾斜角度"), {
      target: { value: "-12" },
    });
    fireEvent.change(screen.getByLabelText("文字横向位置"), {
      target: { value: "20" },
    });
    fireEvent.change(screen.getByLabelText("文字纵向位置"), {
      target: { value: "35" },
    });
    fireEvent.click(coverButton);

    const posterPreview = await screen.findByRole("img", {
      name: "Poster preview",
    });
    expect(posterPreview).toBeTruthy();
    const coverCall = calls.find(
      (call) =>
        call.method === "POST" && call.url === "/api/local-metadata/cover-preview",
    );
    expect(coverCall?.body).toMatchObject({
      title: "Poster Manual\nFrame Source",
      title_angle_degrees: -12,
      title_position_x_percent: 20,
      title_position_y_percent: 35,
      template: "simple_poster",
      title_font_id: "source_han_sans",
      selected_frame_ids: ["frames/frame-a.jpg"],
    });

    fireEvent.click(screen.getByRole("button", { name: "生成整理预览" }));
    await screen.findByText("计划 plan-local");
    const planCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/local-metadata/preview-plan",
    );
    expect(planCall?.body).toMatchObject({
      metadata: {
        title: "Frame Source",
      },
      poster_ref: "covers/poster.jpg",
      fanart_ref: "covers/fanart.jpg",
      selected_frame_ids: ["frames/frame-a.jpg"],
    });
    await screen.findByText("<movie><title>Frame Source</title></movie>");

    fireEvent.change(screen.getByLabelText("文字横向位置"), {
      target: { value: "55" },
    });
    expect(screen.queryByRole("img", { name: "Poster preview" })).toBeNull();
    expect(screen.queryByText("计划 plan-local")).toBeNull();
    expect(
      screen.queryByText("<movie><title>Frame Source</title></movie>"),
    ).toBeNull();

    fireEvent.click(coverButton);
    await screen.findByRole("img", { name: "Poster preview" });
    fireEvent.click(screen.getByRole("button", { name: "生成整理预览" }));
    await screen.findByText("计划 plan-local");

    fireEvent.change(screen.getByLabelText("封面文字"), {
      target: { value: "Poster Manual Updated" },
    });
    expect(screen.queryByRole("img", { name: "Poster preview" })).toBeNull();
    expect(screen.queryByText("计划 plan-local")).toBeNull();

    fireEvent.change(screen.getByLabelText("模板"), {
      target: { value: "jav_classic_left_strip" },
    });
    expect(screen.getByLabelText("封面字体")).toHaveValue("dela_gothic_one");
    expect(screen.queryByRole("img", { name: "Poster preview" })).toBeNull();
    expect(screen.queryByText("计划 plan-local")).toBeNull();

    fireEvent.change(screen.getByLabelText("封面字体"), {
      target: { value: "lxgw_wenkai" },
    });
    expect(screen.getByLabelText("封面字体")).toHaveValue("lxgw_wenkai");
    fireEvent.change(screen.getByLabelText("模板"), {
      target: { value: "tangxin_vlog" },
    });
    expect(screen.getByLabelText("封面字体")).toHaveValue("lxgw_wenkai");

    fireEvent.click(coverButton);
    await screen.findByRole("img", { name: "Poster preview" });
    fireEvent.click(screen.getByRole("button", { name: "生成整理预览" }));
    await screen.findByText("计划 plan-local");

    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "Retitled Frame Source" },
    });
    expect(screen.queryByRole("img", { name: "Poster preview" })).toBeNull();
    expect(screen.queryByText("计划 plan-local")).toBeNull();
  });

  it("executes only the current non-preview local plan", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/preview-plan",
        response: {
          plan_id: "plan-copy",
          metadata: { title: "Executable Source" },
          materialized_assets: [],
          nfo_xml: "<movie><title>Executable Source</title></movie>",
          plan: operationPlanFixture({ plan_id: "plan-copy", mode: "copy" }),
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/plans/plan-copy/execute",
        response: {
          plan_id: "plan-copy",
          job_id: null,
          state: "completed",
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );
    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Executable.Source.mp4" },
    });
    fireEvent.change(screen.getByLabelText("模式"), {
      target: { value: "copy" },
    });

    const executeButton = screen.getByRole("button", {
      name: "按当前预览执行整理",
    });
    expect(executeButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "生成整理预览" }));
    await screen.findByText("计划 plan-copy");
    expect(executeButton).not.toBeDisabled();

    fireEvent.click(executeButton);
    await waitFor(() =>
      expect(screen.getAllByText(/整理完成/).length).toBeGreaterThan(0),
    );
    const executeCall = calls.find(
      (call) =>
        call.method === "POST" &&
        call.url === "/api/local-metadata/plans/plan-copy/execute",
    );
    expect(executeCall?.body).toMatchObject({ approved: true, plan_version: 1 });

    fireEvent.change(screen.getByLabelText("文字纵向位置"), {
      target: { value: "45" },
    });
    expect(screen.queryByText("计划 plan-copy")).toBeNull();
    expect(screen.queryByText(/整理完成/)).toBeNull();
    expect(executeButton).toBeDisabled();
  });
});

function settingsFixture(): AppSettings {
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

function operationPlanFixture(
  overrides: Partial<{ plan_id: string; mode: string }> = {},
) {
  return {
    plan_id: overrides.plan_id ?? "plan-local",
    version: 1,
    job_id: null,
    mode: overrides.mode ?? "preview",
    destination_root: "/media/organized",
    target_directory: "/media/organized/Metadata Title",
    source_snapshot: [],
    materialized_asset_cache_paths: [],
    steps: [],
    conflicts: [],
    safety_warnings: [],
    created_at: "2026-07-27T00:00:00",
  };
}

function scannedVideoFixture(
  overrides: Partial<{
    path: string;
    filename: string;
    cleaned_title: string;
    default_organize_filename: string;
    size_bytes: number;
  }> = {},
) {
  return {
    path: "/media/incoming/Video.mp4",
    filename: "Video.mp4",
    cleaned_title: "Video",
    default_organize_filename: "Video",
    size_bytes: 1024,
    mtime_ns: 1,
    group_key: "video",
    multipart_index: null,
    ...overrides,
  };
}

function cachedAssetFixture(
  overrides: Partial<{
    id: string;
    kind: string;
    url: string;
    cache_path: string;
    content_type: string;
    size_bytes: number;
    sha256: string;
    width: number | null;
    height: number | null;
    time_seconds: number | null;
  }> = {},
) {
  return {
    id: "frames/frame.jpg",
    kind: "frame",
    url: "/api/local-metadata/cache/frames/frame.jpg",
    cache_path: "/tmp/frame.jpg",
    content_type: "image/jpeg",
    size_bytes: 512,
    sha256: "abc123",
    width: 1280,
    height: 720,
    time_seconds: null,
    ...overrides,
  };
}
