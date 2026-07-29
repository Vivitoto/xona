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
        path: "/api/local-metadata/frames",
        response: {
          video_path: "/media/incoming/Raw.Local.Work.mp4",
          frames: [],
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
    fireEvent.click(screen.getByRole("button", { name: "分析并生成截图" }));

    const organizeInput = screen.getByLabelText("整理文件名") as HTMLInputElement;
    await waitFor(() => expect(organizeInput).toHaveValue("Cleaned Local Work"));

    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "Metadata Title" },
    });
    fireEvent.change(organizeInput, {
      target: { value: "Custom Output Name" },
    });
    fireEvent.change(screen.getByLabelText("额外背景图数量"), {
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
        technical: {
          width: 1920,
          height: 1080,
          video_codec: "h264",
          audio_codec: "aac",
          bit_rate: 5000000,
          fps: 29.97,
        },
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
    fireEvent.change(batch.getByLabelText("演员"), {
      target: { value: "Actor One\nActor Two" },
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
    expect(editor.getByLabelText("演员")).toHaveValue("Actor One\nActor Two");
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
        actors: ["Actor One", "Actor Two"],
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

  it("applies default batch random title format to loaded cover previews", async () => {
    const selectedFrameIds = Array.from(
      { length: 9 },
      (_, index) => `frames/beta-${index + 1}.jpg`,
    );
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
              default_organize_filename: "Beta Scene",
              size_bytes: 4096,
            }),
          ],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/analyze",
        response: {
          video_path: "/media/incoming/Beta.Scene.mkv",
          cleaned_title: "Beta Scene",
          default_organize_filename: "Beta Scene",
          default_plot: "Local metadata generated for Beta.Scene.mkv.",
          default_tags: ["local-generated", "unmatched"],
          technical: {
            path: "/media/incoming/Beta.Scene.mkv",
            size_bytes: 4096,
            duration_seconds: 180,
            width: 1920,
            height: 1080,
            video_codec: "h264",
            audio_codec: "aac",
            format_name: "matroska",
            bit_rate: 6000000,
            fps: 29.97,
          },
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/frames",
        response: {
          video_path: "/media/incoming/Beta.Scene.mkv",
          frames: selectedFrameIds.map((id, index) =>
            cachedAssetFixture({
              id,
              url: `/api/local-metadata/cache/${id}`,
              time_seconds: (index + 1) * 15,
            }),
          ),
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/cover-preview",
        response: {
          poster: cachedAssetFixture({
            id: "covers/beta-poster.jpg",
            kind: "poster",
            url: "/api/local-metadata/cache/covers/beta-poster.jpg",
            width: 900,
            height: 1350,
          }),
          fanart: cachedAssetFixture({
            id: "covers/beta-fanart.jpg",
            kind: "fanart",
            url: "/api/local-metadata/cache/covers/beta-fanart.jpg",
            width: 1600,
            height: 900,
          }),
          thumb: cachedAssetFixture({
            id: "covers/beta-thumb.jpg",
            kind: "thumb",
            url: "/api/local-metadata/cache/covers/beta-thumb.jpg",
            width: 1600,
            height: 900,
          }),
          template: "tangxin_vlog",
          title_font_id: "lxgw_wenkai",
          selected_frame_ids: selectedFrameIds,
          warnings: [],
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );

    const singleTab = screen.getByRole("tab", { name: "单个整理" });
    const batchTab = screen.getByRole("tab", { name: "批量整理" });
    fireEvent.click(batchTab);

    const batchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(batchSection).toBeTruthy();
    const batch = within(batchSection as HTMLElement);

    expect(batch.getByRole("heading", { name: "批量封面风格" })).toBeTruthy();
    expect(batch.getByText(/字号\s+\+\/-10px/)).toBeTruthy();
    expect(batch.getByText(/角度\s+\+\/-5 度/)).toBeTruthy();
    expect(batch.getByText(/位置\s+\+\/-10/)).toBeTruthy();
    expect(batch.getByLabelText("随机标题格式")).toBeChecked();
    expect(batch.getByLabelText("批量模板")).toBeTruthy();
    expect(batch.getByLabelText("批量标题字体")).toBeTruthy();
    expect(batch.getByLabelText("基础字号")).toBeTruthy();
    expect(batch.getByLabelText("基础填充色")).toBeTruthy();
    expect(batch.getByLabelText("基础描边色")).toBeTruthy();
    expect(batch.getByLabelText("基础描边宽度")).toBeTruthy();
    expect(batch.getByLabelText("批量文字效果")).toBeTruthy();
    expect(batch.getByLabelText("基础倾斜角度")).toBeTruthy();
    expect(batch.getByLabelText("基础横向偏移")).toBeTruthy();
    expect(batch.getByLabelText("基础纵向偏移")).toBeTruthy();
    expect(batch.queryByLabelText("字号随机范围 +/-")).toBeNull();
    expect(batch.queryByLabelText("角度随机范围 +/-")).toBeNull();
    expect(batch.queryByLabelText("横向偏移随机范围 +/-")).toBeNull();
    expect(batch.queryByLabelText("纵向偏移随机范围 +/-")).toBeNull();
    expect(
      batch.queryByRole("checkbox", { name: "镜像倾斜方向" }),
    ).toBeNull();
    expect(batch.getByLabelText("批量并发数")).toBeTruthy();

    fireEvent.change(batch.getByLabelText("目录路径"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(batch.getByRole("button", { name: "扫描目录" }));
    await waitFor(() => expect(batch.getByText("Beta.Scene.mkv")).toBeTruthy());

    fireEvent.change(batch.getByLabelText("批量模板"), {
      target: { value: "tangxin_vlog" },
    });
    expect(batch.getByLabelText("批量标题字体")).toHaveValue("smiley_sans");
    fireEvent.change(batch.getByLabelText("批量标题字体"), {
      target: { value: "lxgw_wenkai" },
    });
    fireEvent.change(batch.getByLabelText("基础字号"), {
      target: { value: "80" },
    });
    fireEvent.change(batch.getByLabelText("基础填充色"), {
      target: { value: "#808080" },
    });
    fireEvent.change(batch.getByLabelText("基础描边色"), {
      target: { value: "#808080" },
    });
    fireEvent.change(batch.getByLabelText("基础描边宽度"), {
      target: { value: "3" },
    });
    fireEvent.change(batch.getByLabelText("批量文字效果"), {
      target: { value: "glow" },
    });
    fireEvent.change(batch.getByLabelText("基础倾斜角度"), {
      target: { value: "10" },
    });
    fireEvent.change(batch.getByLabelText("基础横向偏移"), {
      target: { value: "4" },
    });
    fireEvent.change(batch.getByLabelText("基础纵向偏移"), {
      target: { value: "-6" },
    });

    fireEvent.click(batch.getByRole("button", { name: "为已选视频生成整理信息" }));
    await waitFor(() => expect(batch.getByText("已生成的整理信息")).toBeTruthy());
    expect(batch.getAllByText(/TangXin Vlog/).length).toBeGreaterThan(1);

    fireEvent.click(
      batch.getByRole("button", { name: "载入整理信息 Beta.Scene.mkv" }),
    );
    fireEvent.click(singleTab);

    let editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    let editor = within(editorSection as HTMLElement);
    await waitFor(() => expect(editor.getByLabelText("模板")).toHaveValue("tangxin_vlog"));
    const computedSettings = readCoverSettings(editorSection as HTMLElement);
    expect(computedSettings.titleFontId).not.toBe("lxgw_wenkai");
    expect(computedSettings.titleFontId).toMatch(
      /^(source_han_sans|noto_sans_jp|dela_gothic_one|bebas_neue|anton|smiley_sans|zcool_qingke_huangyou|lxgw_wenkai)$/,
    );
    expect(computedSettings.titleFontSize).toBeGreaterThanOrEqual(70);
    expect(computedSettings.titleFontSize).toBeLessThanOrEqual(90);
    expect(Math.abs(computedSettings.titleAngleDegrees)).toBeGreaterThanOrEqual(5);
    expect(Math.abs(computedSettings.titleAngleDegrees)).toBeLessThanOrEqual(15);
    expect(computedSettings.titleOffsetX).toBeGreaterThanOrEqual(-6);
    expect(computedSettings.titleOffsetX).toBeLessThanOrEqual(14);
    expect(computedSettings.titleOffsetY).toBeGreaterThanOrEqual(-16);
    expect(computedSettings.titleOffsetY).toBeLessThanOrEqual(4);
    expect(computedSettings.titleFillColor).not.toBe("#808080");
    expect(computedSettings.titleStrokeColor).not.toBe("#808080");
    expect(computedSettings.titleFillColor).not.toBe(computedSettings.titleStrokeColor);
    expect(
      colorContrastRatio(
        computedSettings.titleFillColor,
        computedSettings.titleStrokeColor,
      ),
    ).toBeGreaterThanOrEqual(4.5);

    fireEvent.click(batchTab);
    const regeneratedBatchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(regeneratedBatchSection).toBeTruthy();
    const regeneratedBatch = within(regeneratedBatchSection as HTMLElement);
    fireEvent.click(
      regeneratedBatch.getByRole("button", { name: "为已选视频生成整理信息" }),
    );
    fireEvent.click(singleTab);
    editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    editor = within(editorSection as HTMLElement);
    await waitFor(() =>
      expect(readCoverSettings(editorSection as HTMLElement)).toEqual(computedSettings),
    );

    fireEvent.click(screen.getByRole("button", { name: "分析并生成截图" }));
    await screen.findByRole("button", { name: /截图 0:15/ });
    expect(readCoverSettings(editorSection as HTMLElement)).toEqual(computedSettings);

    fireEvent.click(screen.getByRole("button", { name: "生成封面预览" }));
    await screen.findByRole("img", { name: "Poster preview" });
    const coverCall = calls.find(
      (call) =>
        call.method === "POST" && call.url === "/api/local-metadata/cover-preview",
    );
    expect(coverCall?.body).toMatchObject({
      video_path: "/media/incoming/Beta.Scene.mkv",
      template: computedSettings.template,
      title_font_id: computedSettings.titleFontId,
      title_font_size: computedSettings.titleFontSize,
      title_fill_color: computedSettings.titleFillColor,
      title_stroke_color: computedSettings.titleStrokeColor,
      title_stroke_width: computedSettings.titleStrokeWidth,
      title_effect: computedSettings.titleEffect,
      title_angle_degrees: computedSettings.titleAngleDegrees,
      title_position_x_percent: computedSettings.titleOffsetX + 50,
      title_position_y_percent: computedSettings.titleOffsetY + 50,
      selected_frame_ids: selectedFrameIds,
    });

    fireEvent.change(editor.getByLabelText("封面字号"), {
      target: { value: "91" },
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
    expect(updatedBatch.getByText(/91px/)).toBeTruthy();
    fireEvent.click(
      updatedBatch.getByRole("button", { name: "载入整理信息 Beta.Scene.mkv" }),
    );
    fireEvent.click(singleTab);
    editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    editor = within(editorSection as HTMLElement);
    await waitFor(() => expect(editor.getByLabelText("封面字号")).toHaveValue(91));
  });

  it("keeps batch cover baseline stable when random title format is disabled", async () => {
    installFetchMock([
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
              default_organize_filename: "Beta Scene",
              size_bytes: 4096,
            }),
          ],
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );

    const singleTab = screen.getByRole("tab", { name: "单个整理" });
    const batchTab = screen.getByRole("tab", { name: "批量整理" });
    fireEvent.click(batchTab);

    const batchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(batchSection).toBeTruthy();
    const batch = within(batchSection as HTMLElement);

    fireEvent.change(batch.getByLabelText("目录路径"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(batch.getByRole("button", { name: "扫描目录" }));
    await waitFor(() => expect(batch.getByText("Beta.Scene.mkv")).toBeTruthy());

    expect(batch.getByLabelText("随机标题格式")).toBeChecked();
    fireEvent.click(batch.getByLabelText("随机标题格式"));
    expect(batch.getByLabelText("随机标题格式")).not.toBeChecked();
    fireEvent.change(batch.getByLabelText("批量模板"), {
      target: { value: "tangxin_vlog" },
    });
    fireEvent.change(batch.getByLabelText("批量标题字体"), {
      target: { value: "lxgw_wenkai" },
    });
    fireEvent.change(batch.getByLabelText("基础字号"), {
      target: { value: "80" },
    });
    fireEvent.change(batch.getByLabelText("基础填充色"), {
      target: { value: "#808080" },
    });
    fireEvent.change(batch.getByLabelText("基础描边色"), {
      target: { value: "#808080" },
    });
    fireEvent.change(batch.getByLabelText("基础描边宽度"), {
      target: { value: "3" },
    });
    fireEvent.change(batch.getByLabelText("批量文字效果"), {
      target: { value: "glow" },
    });
    fireEvent.change(batch.getByLabelText("基础倾斜角度"), {
      target: { value: "10" },
    });
    fireEvent.change(batch.getByLabelText("基础横向偏移"), {
      target: { value: "4" },
    });
    fireEvent.change(batch.getByLabelText("基础纵向偏移"), {
      target: { value: "-6" },
    });

    fireEvent.click(batch.getByRole("button", { name: "为已选视频生成整理信息" }));
    await waitFor(() => expect(batch.getByText("已生成的整理信息")).toBeTruthy());
    fireEvent.click(
      batch.getByRole("button", { name: "载入整理信息 Beta.Scene.mkv" }),
    );
    fireEvent.click(singleTab);

    let editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    await waitFor(() =>
      expect(readCoverSettings(editorSection as HTMLElement)).toEqual({
        template: "tangxin_vlog",
        titleFontId: "lxgw_wenkai",
        titleFontSize: 80,
        titleFillColor: "#808080",
        titleStrokeColor: "#808080",
        titleStrokeWidth: 3,
        titleEffect: "glow",
        titleAngleDegrees: 10,
        titleOffsetX: 4,
        titleOffsetY: -6,
      }),
    );

    fireEvent.click(batchTab);
    const regeneratedBatchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(regeneratedBatchSection).toBeTruthy();
    const regeneratedBatch = within(regeneratedBatchSection as HTMLElement);
    fireEvent.click(
      regeneratedBatch.getByRole("button", { name: "为已选视频生成整理信息" }),
    );
    fireEvent.click(singleTab);
    editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    await waitFor(() =>
      expect(readCoverSettings(editorSection as HTMLElement)).toEqual({
        template: "tangxin_vlog",
        titleFontId: "lxgw_wenkai",
        titleFontSize: 80,
        titleFillColor: "#808080",
        titleStrokeColor: "#808080",
        titleStrokeWidth: 3,
        titleEffect: "glow",
        titleAngleDegrees: 10,
        titleOffsetX: 4,
        titleOffsetY: -6,
      }),
    );
  });

  it("generates batch NFO cover and plans with logs while continuing after one item fails", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/scan",
        response: {
          scanned_count: 3,
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
              default_organize_filename: "Beta Scene",
              size_bytes: 4096,
            }),
            scannedVideoFixture({
              path: "/media/incoming/Gamma.Scene.mp4",
              filename: "Gamma.Scene.mp4",
              cleaned_title: "Gamma Scene",
              default_organize_filename: "Gamma Scene",
              size_bytes: 8192,
            }),
          ],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/analyze",
        response: (call) => {
          const videoPath = requestVideoPath(call.body);
          return analyzeResponseFixture(videoPath);
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/frames",
        response: (call) => {
          const videoPath = requestVideoPath(call.body);
          if (videoPath.includes("Beta.Scene")) {
            throw new Error("Beta screenshots failed");
          }
          const stem = slugFromPath(videoPath);
          return {
            video_path: videoPath,
            frames: Array.from({ length: 9 }, (_, index) =>
              cachedAssetFixture({
                id: `frames/${stem}-${index + 1}.jpg`,
                url: `/api/local-metadata/cache/frames/${stem}-${index + 1}.jpg`,
                time_seconds: (index + 1) * 20,
              }),
            ),
            warnings: [],
          };
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/cover-preview",
        response: (call) => {
          const videoPath = requestVideoPath(call.body);
          const stem = slugFromPath(videoPath);
          return {
            poster: cachedAssetFixture({
              id: `covers/${stem}-poster.jpg`,
              kind: "poster",
              url: `/api/local-metadata/cache/covers/${stem}-poster.jpg`,
              width: 900,
              height: 1350,
            }),
            fanart: cachedAssetFixture({
              id: `covers/${stem}-fanart.jpg`,
              kind: "fanart",
              url: `/api/local-metadata/cache/covers/${stem}-fanart.jpg`,
              width: 1600,
              height: 900,
            }),
            thumb: cachedAssetFixture({
              id: `covers/${stem}-thumb.jpg`,
              kind: "thumb",
              url: `/api/local-metadata/cache/covers/${stem}-thumb.jpg`,
              width: 1600,
              height: 900,
            }),
            template: "simple_poster",
            title_font_id: "source_han_sans",
            selected_frame_ids: Array.from(
              { length: 9 },
              (_, index) => `frames/${stem}-${index + 1}.jpg`,
            ),
            warnings: [],
          };
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/preview-plan",
        response: (call) => {
          const videoPath = requestPlanVideoPath(call.body);
          const stem = slugFromPath(videoPath);
          return {
            plan_id: `plan-${stem}`,
            metadata: { title: requestPlanTitle(call.body) },
            materialized_assets: [],
            nfo_xml: `<movie><title>${requestPlanTitle(call.body)}</title></movie>`,
            plan: operationPlanFixture({
              plan_id: `plan-${stem}`,
              mode: "copy",
            }),
          };
        },
      },
      {
        method: "POST",
        path: /\/api\/local-metadata\/plans\/plan-(alpha-scene|gamma-scene)\/execute/,
        response: (call) => ({
          plan_id: call.url.includes("alpha-scene")
            ? "plan-alpha-scene"
            : "plan-gamma-scene",
          job_id: null,
          state: "completed",
        }),
      },
      {
        method: "POST",
        path: /\/api\/local-metadata\/plans\/plan-(alpha-scene|gamma-scene)\/cleanup-cache/,
        response: (call) => ({
          plan_id: call.url.includes("alpha-scene")
            ? "plan-alpha-scene"
            : "plan-gamma-scene",
          deleted_directories: 1,
          deleted_files: 12,
          cache_dirs: ["/config/cache/local_metadata/ab/abcdef"],
          warnings: [],
        }),
      },
    ]);

    render(<UnmatchedVideosPage />);

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );

    fireEvent.click(screen.getByRole("tab", { name: "批量整理" }));
    const batchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(batchSection).toBeTruthy();
    const batch = within(batchSection as HTMLElement);

    fireEvent.change(batch.getByLabelText("目录路径"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(batch.getByRole("button", { name: "扫描目录" }));
    await waitFor(() => expect(batch.getByText("Gamma.Scene.mp4")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("模式"), {
      target: { value: "copy" },
    });
    fireEvent.change(batch.getByLabelText("批量并发数"), {
      target: { value: "2" },
    });
    fireEvent.click(batch.getByRole("button", { name: "为已选视频生成整理信息" }));
    await waitFor(() => expect(batch.getByText("已生成的整理信息")).toBeTruthy());

    const generateButton = batch.getByRole("button", {
      name: "生成批量 NFO/封面/整理预览",
    });
    fireEvent.click(generateButton);

    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "批量生成摘要" }),
      ).toHaveTextContent("成功 2 个，失败 1 个"),
    );
    expect(screen.getByText("失败：Beta screenshots failed")).toBeTruthy();
    expect(screen.getByText("计划 plan-alpha-scene")).toBeTruthy();
    expect(screen.getByText("计划 plan-gamma-scene")).toBeTruthy();
    expect(screen.queryByText("计划 plan-beta-scene")).toBeNull();
    expect(screen.getAllByText("已生成").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("生成失败")).toBeTruthy();

    expect(
      calls.some((call) => call.url.includes("/execute")),
    ).toBe(false);
    expect(
      calls.some((call) => call.url.includes("/cleanup-cache")),
    ).toBe(false);
    expect(
      calls.filter(
        (call) =>
          call.method === "POST" && call.url === "/api/local-metadata/analyze",
      ),
    ).toHaveLength(3);
    expect(
      calls.filter(
        (call) =>
          call.method === "POST" && call.url === "/api/local-metadata/frames",
      ),
    ).toHaveLength(3);
    expect(
      calls.filter(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/local-metadata/cover-preview",
      ),
    ).toHaveLength(2);
    expect(
      calls.filter(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/local-metadata/preview-plan",
      ),
    ).toHaveLength(2);

    fireEvent.click(
      batch.getByRole("button", {
        name: "执行已生成的批量整理计划",
      }),
    );
    await waitFor(() =>
      expect(screen.getAllByText("已执行")).toHaveLength(2),
    );
    await waitFor(() =>
      expect(screen.getAllByText(/本地元数据缓存已清理：1 个目录，12 个文件/)).toHaveLength(2),
    );
    expect(
      calls.filter((call) => call.url.includes("/execute")),
    ).toHaveLength(2);
    const cleanupCalls = calls.filter((call) => call.url.includes("/cleanup-cache"));
    expect(cleanupCalls).toHaveLength(2);
    cleanupCalls.forEach((call) => {
      expect(call.body).toMatchObject({ plan_version: 1 });
    });
    expect(
      calls.some((call) => call.url.includes("plan-beta-scene/execute")),
    ).toBe(false);
  });

  it("requires selected frames for cover preview and clears stale cover and plan previews", async () => {
    const selectedFrameIds = Array.from(
      { length: 9 },
      (_, index) => `frames/frame-${index + 1}.jpg`,
    );
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
          frames: selectedFrameIds.map((id, index) =>
            cachedAssetFixture({
              id,
              url: `/api/local-metadata/cache/${id}`,
              time_seconds: index === 0 ? 12 : (index + 1) * 30,
            }),
          ),
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
          thumb: cachedAssetFixture({
            id: "covers/thumb.jpg",
            kind: "thumb",
            url: "/api/local-metadata/cache/covers/thumb.jpg",
            width: 1600,
            height: 900,
          }),
          template: "simple_poster",
          title_font_id: "source_han_sans",
          selected_frame_ids: selectedFrameIds,
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
    expect(screen.getByText(/自动选中前 9 张作为/)).toBeTruthy();
    expect(screen.getByText(/0 表示居中/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "分析并生成截图" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "分析" })).toBeNull();
    expect(screen.queryByRole("button", { name: "生成截图" })).toBeNull();

    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Frame.Source.mp4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析并生成截图" }));
    await waitFor(() =>
      expect(screen.getByLabelText("标题")).toHaveValue("Frame Source"),
    );
    expect(screen.getByLabelText("封面文字")).toHaveValue("Frame Source");
    expect(screen.getByLabelText("封面字体")).toHaveValue("source_han_sans");
    expect(screen.getByLabelText("封面字号")).toHaveValue(74);
    expect(screen.getByLabelText("文字填充色")).toHaveValue("#ffffff");
    expect(screen.getByLabelText("描边颜色")).toHaveValue("#0c1114");
    expect(screen.getByLabelText("描边宽度")).toHaveValue(4);
    expect(screen.getByLabelText("文字效果")).toHaveValue("shadow");
    expect(screen.getByLabelText("文字倾斜角度")).toHaveValue(-8);
    expect(screen.getByLabelText("文字横向偏移")).toHaveValue(0);
    expect(screen.getByLabelText("文字纵向偏移")).toHaveValue(43);

    const coverButton = screen.getByRole("button", { name: "生成封面预览" });
    const resetFramesButton = screen.getByRole("button", { name: "重新选择前 9 张" });
    const firstFrame = await screen.findByRole("button", { name: /截图 0:12/ });
    const framesCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/local-metadata/frames",
    );
    expect(framesCall?.body).toMatchObject({
      video_path: "/media/incoming/Frame.Source.mp4",
      frame_count: 9,
    });
    expect(screen.getByText(/Xona 默认选择前 9 张；当前已选择 9 张/)).toBeTruthy();
    expect(coverButton).not.toBeDisabled();
    expect(resetFramesButton).toBeDisabled();

    fireEvent.click(firstFrame);
    expect(screen.getByText(/Xona 默认选择前 9 张；当前已选择 8 张/)).toBeTruthy();
    expect(coverButton).toBeDisabled();
    expect(resetFramesButton).not.toBeDisabled();

    fireEvent.click(resetFramesButton);
    expect(screen.getByText(/Xona 默认选择前 9 张；当前已选择 9 张/)).toBeTruthy();
    expect(coverButton).not.toBeDisabled();
    expect(resetFramesButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText("封面文字"), {
      target: { value: "Poster Manual\nFrame Source" },
    });
    fireEvent.change(screen.getByLabelText("文字倾斜角度"), {
      target: { value: "-12" },
    });
    fireEvent.change(screen.getByLabelText("文字横向偏移"), {
      target: { value: "-30" },
    });
    fireEvent.change(screen.getByLabelText("文字纵向偏移"), {
      target: { value: "-15" },
    });
    fireEvent.change(screen.getByLabelText("封面字号"), {
      target: { value: "52" },
    });
    fireEvent.change(screen.getByLabelText("文字填充色"), {
      target: { value: "#f8fafc" },
    });
    fireEvent.change(screen.getByLabelText("描边颜色"), {
      target: { value: "#e11d48" },
    });
    fireEvent.change(screen.getByLabelText("描边宽度"), {
      target: { value: "0" },
    });
    fireEvent.change(screen.getByLabelText("文字效果"), {
      target: { value: "none" },
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
      title_font_size: 52,
      title_fill_color: "#f8fafc",
      title_stroke_color: "#e11d48",
      title_stroke_width: 0,
      title_effect: "none",
      selected_frame_ids: selectedFrameIds,
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
      thumb_ref: "covers/thumb.jpg",
      selected_frame_ids: selectedFrameIds,
    });
    await screen.findByText("<movie><title>Frame Source</title></movie>");

    fireEvent.change(screen.getByLabelText("文字横向偏移"), {
      target: { value: "5" },
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
    expect(screen.getByLabelText("封面字号")).toHaveValue(62);
    expect(screen.getByLabelText("文字填充色")).toHaveValue("#121b22");
    expect(screen.getByLabelText("描边颜色")).toHaveValue("#ffffff");
    expect(screen.getByLabelText("描边宽度")).toHaveValue(1);
    expect(screen.getByLabelText("文字效果")).toHaveValue("shadow");
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

    fireEvent.change(screen.getByLabelText("文字纵向偏移"), {
      target: { value: "-5" },
    });
    expect(screen.queryByText("计划 plan-copy")).toBeNull();
    expect(screen.queryByText(/整理完成/)).toBeNull();
    expect(executeButton).toBeDisabled();
  });

  it("makes screenshot count configurable and keeps many thumbnails in a bounded scroller", async () => {
    const frameAssets = Array.from({ length: 12 }, (_, index) =>
      cachedAssetFixture({
        id: `frames/frame-${index + 1}.jpg`,
        url: `/api/local-metadata/cache/frames/frame-${index + 1}.jpg`,
        time_seconds: (index + 1) * 10,
      }),
    );
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/analyze",
        response: {
          video_path: "/media/incoming/Many.Frames.mp4",
          cleaned_title: "Many Frames",
          default_organize_filename: "Many Frames",
          default_plot: "Local metadata generated for Many.Frames.mp4.",
          default_tags: ["local-generated", "unmatched"],
          technical: {
            path: "/media/incoming/Many.Frames.mp4",
            size_bytes: 4,
            duration_seconds: 360,
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
          video_path: "/media/incoming/Many.Frames.mp4",
          frames: frameAssets,
          warnings: [],
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );
    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Many.Frames.mp4" },
    });
    fireEvent.change(screen.getByLabelText("截图数量"), {
      target: { value: "12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析并生成截图" }));

    await screen.findByRole("button", { name: /截图 0:10/ });
    expect(screen.getByText(/Xona 默认选择前 9 张；当前已选择 9 张/)).toBeTruthy();
    expect(screen.getByLabelText("截图候选").closest(".frame-strip")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /截图 / })).toHaveLength(12);
    const framesCall = calls.find(
      (call) => call.method === "POST" && call.url === "/api/local-metadata/frames",
    );
    expect(framesCall?.body).toMatchObject({
      video_path: "/media/incoming/Many.Frames.mp4",
      frame_count: 12,
    });
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

function analyzeResponseFixture(videoPath: string) {
  const title = titleFromPathFixture(videoPath);
  const filename = videoPath.split("/").pop() ?? videoPath;
  return {
    video_path: videoPath,
    cleaned_title: title,
    default_organize_filename: title,
    default_plot: `Local metadata generated for ${filename}.`,
    default_tags: ["local-generated", "unmatched"],
    technical: {
      path: videoPath,
      size_bytes: 4096,
      duration_seconds: 180,
      width: 1920,
      height: 1080,
      video_codec: "h264",
      audio_codec: "aac",
      format_name: "mp4",
      bit_rate: 6000000,
      fps: 29.97,
    },
    warnings: [],
  };
}

function requestVideoPath(body: unknown): string {
  if (
    body &&
    typeof body === "object" &&
    "video_path" in body &&
    typeof body.video_path === "string"
  ) {
    return body.video_path;
  }
  throw new Error("Expected request body with video_path");
}

function requestPlanVideoPath(body: unknown): string {
  const metadata = requestPlanMetadata(body);
  if (typeof metadata.video_path === "string") {
    return metadata.video_path;
  }
  throw new Error("Expected plan request metadata with video_path");
}

function requestPlanTitle(body: unknown): string {
  const metadata = requestPlanMetadata(body);
  if (typeof metadata.title === "string") {
    return metadata.title;
  }
  throw new Error("Expected plan request metadata with title");
}

function requestPlanMetadata(body: unknown): Record<string, unknown> {
  if (
    body &&
    typeof body === "object" &&
    "metadata" in body &&
    body.metadata &&
    typeof body.metadata === "object"
  ) {
    return body.metadata as Record<string, unknown>;
  }
  throw new Error("Expected plan request body with metadata");
}

function slugFromPath(path: string): string {
  return titleFromPathFixture(path).toLowerCase().replace(/\s+/g, "-");
}

function titleFromPathFixture(path: string): string {
  const filename = path.split(/[\\/]/).pop() ?? path;
  return filename
    .replace(/\.[^.]+$/, "")
    .replace(/[._-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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

function colorContrastRatio(firstColor: string, secondColor: string): number {
  const first = parseHexColor(firstColor);
  const second = parseHexColor(secondColor);
  if (!first || !second) {
    return 0;
  }
  const firstLuminance = relativeLuminance(first);
  const secondLuminance = relativeLuminance(second);
  const lighter = Math.max(firstLuminance, secondLuminance);
  const darker = Math.min(firstLuminance, secondLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

function parseHexColor(value: string): [number, number, number] | null {
  const match = /^#([0-9a-f]{6})$/.exec(value);
  if (!match) {
    return null;
  }
  const hex = match[1];
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ];
}

function relativeLuminance([red, green, blue]: [number, number, number]): number {
  return (
    0.2126 * srgbToLinear(red) +
    0.7152 * srgbToLinear(green) +
    0.0722 * srgbToLinear(blue)
  );
}

function srgbToLinear(channel: number): number {
  const normalized = channel / 255;
  return normalized <= 0.03928
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}

function readCoverSettings(container: HTMLElement) {
  const controls = within(container);
  return {
    template: (controls.getByLabelText("模板") as HTMLSelectElement).value,
    titleFontId: (controls.getByLabelText("封面字体") as HTMLSelectElement).value,
    titleFontSize: Number(
      (controls.getByLabelText("封面字号") as HTMLInputElement).value,
    ),
    titleFillColor: (controls.getByLabelText("文字填充色") as HTMLInputElement)
      .value,
    titleStrokeColor: (controls.getByLabelText("描边颜色") as HTMLInputElement)
      .value,
    titleStrokeWidth: Number(
      (controls.getByLabelText("描边宽度") as HTMLInputElement).value,
    ),
    titleEffect: (controls.getByLabelText("文字效果") as HTMLSelectElement).value,
    titleAngleDegrees: Number(
      (controls.getByLabelText("文字倾斜角度") as HTMLInputElement).value,
    ),
    titleOffsetX: Number(
      (controls.getByLabelText("文字横向偏移") as HTMLInputElement).value,
    ),
    titleOffsetY: Number(
      (controls.getByLabelText("文字纵向偏移") as HTMLInputElement).value,
    ),
  };
}
