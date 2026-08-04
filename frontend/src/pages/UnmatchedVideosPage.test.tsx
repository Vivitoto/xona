import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  AppSettings,
  LocalBatchCoverSettings,
  LocalMetadataBatchRead,
  LocalMetadataBatchStatus,
  LocalMetadataDraft,
} from "../api/types";
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
          default_plot: "Cleaned Local Work",
          default_tags: ["{actors}", "{studio}", "{resolution}"],
          default_genres: ["{actors}", "{studio}", "{resolution}"],
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
          plan: operationPlanFixture({ targetStem: "Custom Output Name" }),
        },
      },
    ]);

    render(<UnmatchedVideosPage />);

    expect(screen.getByLabelText("整理文件名 (organize_filename)")).toBeTruthy();
    expect(screen.getByText("留空时使用文件名模板。")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByLabelText("目标目录")).toHaveValue("/media/organized"),
    );

    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Raw.Local.Work.mp4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析并生成截图" }));

    const organizeInput = screen.getByLabelText("整理文件名 (organize_filename)") as HTMLInputElement;
    await waitFor(() => expect(organizeInput).toHaveValue("Cleaned Local Work"));
    expect(screen.getByLabelText("简介 (plot)")).toHaveValue("Cleaned Local Work");
    expect(screen.getByLabelText("标签 (tag)")).toHaveValue("{actors}\n{studio}\n{resolution}");
    expect(screen.getByLabelText("类型 (genre)")).toHaveValue("{actors}\n{studio}\n{resolution}");

    fireEvent.change(screen.getByLabelText("标题 (title)"), {
      target: { value: "Metadata Title" },
    });
    fireEvent.change(organizeInput, {
      target: { value: "Custom Output Name" },
    });
    fireEvent.change(screen.getByLabelText("标签 (tag)"), {
      target: { value: "temporary-tag" },
    });
    fireEvent.change(screen.getByLabelText("标签 (tag)"), {
      target: { value: "" },
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
        plot: "Cleaned Local Work",
        tags: [],
        genres: ["{actors}", "{studio}", "{resolution}"],
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
    expect(await screen.findByText("Custom Output Name.mp4")).toBeTruthy();
    expect(await screen.findByText("Custom Output Name.nfo")).toBeTruthy();
    expect(screen.queryByText("计划步骤")).toBeNull();
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

  it("creates self-contained batch metadata without loading rows into the single editor", async () => {
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
    expect(screen.getByRole("heading", { name: "批量输出规则" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "整理预览" })).toBeNull();
    expect(
      screen.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("等待扫描目录");

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

    fireEvent.change(batch.getByLabelText("标题前缀 (title)"), {
      target: { value: "[Batch] " },
    });
    fireEvent.change(batch.getByLabelText("标题后缀 (title)"), {
      target: { value: " - Draft" },
    });
    fireEvent.change(batch.getByLabelText("整理文件名前缀 (organize_filename)"), {
      target: { value: "OF_" },
    });
    fireEvent.change(batch.getByLabelText("整理文件名后缀 (organize_filename)"), {
      target: { value: "_OUT" },
    });
    fireEvent.change(batch.getByLabelText("制作方 (studio)"), {
      target: { value: "Batch Studio" },
    });
    fireEvent.change(batch.getByLabelText("系列 (set)"), {
      target: { value: "Batch Series" },
    });
    fireEvent.change(batch.getByLabelText("演员 (actor)"), {
      target: { value: "Actor One\nActor Two" },
    });
    fireEvent.change(batch.getByLabelText("标签 (tag)"), {
      target: { value: "batch-tag\nmanual-tag" },
    });
    fireEvent.change(batch.getByLabelText("类型 (genre)"), {
      target: { value: "Drama\nLocal" },
    });
    fireEvent.change(batch.getByLabelText("简介 (plot)"), {
      target: { value: "Batch plot text." },
    });

    fireEvent.click(batch.getByRole("button", { name: "生成批量元数据" }));

    await waitFor(() => expect(batch.getByRole("heading", { name: "已生成的批量元数据" })).toBeTruthy());
    expect(
      batch.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("已生成 2 个批量元数据");
    expect(batch.getByText("[Batch] Alpha Scene - Draft")).toBeTruthy();
    expect(batch.getByText("OF_Alpha Scene_OUT")).toBeTruthy();
    expect(batch.getByText("[Batch] Beta Scene - Draft")).toBeTruthy();
    expect(batch.getByText("OF_Beta Custom_OUT")).toBeTruthy();
    expect(batch.getByText("待提交")).toBeTruthy();
    expect(batch.queryByRole("button", { name: /载入整理信息/ })).toBeNull();
    expect(batch.queryByRole("button", { name: /保存当前草稿/ })).toBeNull();

    fireEvent.click(singleTab);
    const editorSection = screen
      .getByRole("heading", { name: "元数据草稿" })
      .closest("section");
    expect(editorSection).toBeTruthy();
    const editor = within(editorSection as HTMLElement);
    expect(screen.getByLabelText("视频路径")).toHaveValue("");
    expect(editor.getByLabelText("标题 (title)")).toHaveValue("");
  });

  it("selects all scanned batch videos by default and can clear or restore the selection", async () => {
    const videos = Array.from({ length: 7 }, (_, index) => {
      const number = index + 1;
      return scannedVideoFixture({
        path: `/media/incoming/Scene.${number}.mp4`,
        filename: `Scene.${number}.mp4`,
        cleaned_title: `Scene ${number}`,
        default_organize_filename: `Scene ${number}`,
        size_bytes: 1024 * number,
      });
    });
    installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/scan",
        response: {
          scanned_count: videos.length,
          videos,
        },
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

    await waitFor(() => expect(batch.getByText("Scene.7.mp4")).toBeTruthy());
    expect(
      batch.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("已扫描 7 个视频，已选择 7 个");
    expect(batch.getByRole("button", { name: "全选" })).toBeDisabled();
    expect(batch.getByRole("button", { name: "取消全部选中" })).not.toBeDisabled();
    batch
      .getAllByRole("checkbox", { name: /^选择 / })
      .forEach((checkbox) => expect(checkbox).toBeChecked());

    fireEvent.click(batch.getByRole("button", { name: "取消全部选中" }));
    expect(
      batch.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("已扫描 7 个视频，已选择 0 个");
    expect(batch.getByRole("button", { name: "生成批量元数据" })).toBeDisabled();
    expect(batch.getByRole("button", { name: "全选" })).not.toBeDisabled();
    expect(batch.getByRole("button", { name: "取消全部选中" })).toBeDisabled();
    batch
      .getAllByRole("checkbox", { name: /^选择 / })
      .forEach((checkbox) => expect(checkbox).not.toBeChecked());

    fireEvent.click(batch.getByRole("button", { name: "全选" }));
    expect(
      batch.getByRole("status", { name: "批量整理进度" }),
    ).toHaveTextContent("已扫描 7 个视频，已选择 7 个");
    batch
      .getAllByRole("checkbox", { name: /^选择 / })
      .forEach((checkbox) => expect(checkbox).toBeChecked());
  });

  it("shows batch random cover settings as compact row summaries", async () => {
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

    fireEvent.click(screen.getByRole("tab", { name: "批量整理" }));
    const batchSection = screen
      .getByRole("heading", { name: "批量整理列表" })
      .closest("section");
    expect(batchSection).toBeTruthy();
    const batch = within(batchSection as HTMLElement);

    expect(batch.getByRole("heading", { name: "批量封面风格" })).toBeTruthy();
    expect(
      batch.getByText("随机标题格式会按视频路径生成稳定样式；关闭后使用下方基础值。"),
    ).toBeTruthy();
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

    fireEvent.click(batch.getByRole("button", { name: "生成批量元数据" }));
    await waitFor(() => expect(batch.getByRole("heading", { name: "已生成的批量元数据" })).toBeTruthy());
    expect(batch.getAllByText(/TangXin Vlog/).length).toBeGreaterThan(1);
    expect(batch.queryByRole("button", { name: /载入整理信息/ })).toBeNull();
    expect(batch.queryByRole("button", { name: /保存当前草稿/ })).toBeNull();
  });

  it("sends fixed or randomized batch cover settings according to the random title format checkbox", async () => {
    const videoPath = "/media/incoming/Tangxin.Style.mp4";
    const selectedFrameIds = Array.from(
      { length: 9 },
      (_, index) => `frames/tangxin-${index + 1}.jpg`,
    );
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/local-metadata/scan",
        response: {
          scanned_count: 1,
          videos: [
            scannedVideoFixture({
              path: videoPath,
              filename: "Tangxin.Style.mp4",
              cleaned_title: "Tangxin Style",
              default_organize_filename: "Tangxin Style",
              size_bytes: 2048,
            }),
          ],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/batches",
        response: (call) =>
          batchReadFromCreateRequest(call.body, {
            batchId: `batch-${batchCreateBodies(calls).length + 1}`,
          }),
      },
      {
        method: "POST",
        path: "/api/local-metadata/analyze",
        response: analyzeResponseFixture(videoPath),
      },
      {
        method: "POST",
        path: "/api/local-metadata/frames",
        response: {
          video_path: videoPath,
          frames: selectedFrameIds.map((id, index) =>
            cachedAssetFixture({
              id,
              url: `/api/local-metadata/cache/${id}`,
              time_seconds: (index + 1) * 20,
            }),
          ),
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/cover-preview",
        response: (call) => {
          const body = call.body as Record<string, unknown>;
          return {
            poster: cachedAssetFixture({
              id: "covers/tangxin-poster.jpg",
              kind: "poster",
              url: "/api/local-metadata/cache/covers/tangxin-poster.jpg",
              width: 900,
              height: 1350,
            }),
            fanart: cachedAssetFixture({
              id: "covers/tangxin-fanart.jpg",
              kind: "fanart",
              url: "/api/local-metadata/cache/covers/tangxin-fanart.jpg",
              width: 1600,
              height: 900,
            }),
            thumb: cachedAssetFixture({
              id: "covers/tangxin-thumb.jpg",
              kind: "thumb",
              url: "/api/local-metadata/cache/covers/tangxin-thumb.jpg",
              width: 1600,
              height: 900,
            }),
            template: body.template,
            title_font_id: body.title_font_id,
            selected_frame_ids: body.selected_frame_ids,
            warnings: [],
          };
        },
      },
      {
        method: "POST",
        path: "/api/local-metadata/preview-plan",
        response: {
          plan_id: "plan-tangxin-style",
          metadata: { title: "Tangxin Style" },
          materialized_assets: [],
          nfo_xml: "<movie><title>Tangxin Style</title></movie>",
          plan: operationPlanFixture({ plan_id: "plan-tangxin-style" }),
        },
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
    await waitFor(() => expect(batch.getByText("Tangxin.Style.mp4")).toBeTruthy());

    fireEvent.change(batch.getByLabelText("批量模板"), {
      target: { value: "tangxin_vlog" },
    });
    expect(batch.getByLabelText("批量标题字体")).toHaveValue("smiley_sans");

    fireEvent.click(batch.getByLabelText("随机标题格式"));
    expect(batch.getByLabelText("随机标题格式")).not.toBeChecked();
    expect(batch.getByLabelText("相似帧兜底")).toBeChecked();
    expect(batch.getByLabelText("兜底阈值")).toHaveValue(15);
    fireEvent.change(batch.getByLabelText("兜底阈值"), {
      target: { value: "18" },
    });
    fireEvent.change(batch.getByLabelText("批量截图数量"), {
      target: { value: "18" },
    });
    fireEvent.click(batch.getByRole("button", { name: "生成批量元数据" }));
    await waitFor(() => expect(batch.getByRole("heading", { name: "已生成的批量元数据" })).toBeTruthy());
    fireEvent.click(batch.getByRole("button", { name: "提交批量预览任务" }));
    await waitFor(() => expect(batchCreateCoverSettings(calls)).toHaveLength(1));

    const fixedRequest = batchCreateCoverSettings(calls)[0];
    const fixedBaseline = {
      template: "tangxin_vlog",
      title_font_id: "smiley_sans",
      title_font_size: 86,
      title_fill_color: "#ffffff",
      title_stroke_color: "#0e1518",
      title_stroke_width: 6,
      title_effect: "glow",
      title_angle_degrees: -8,
      title_position_x_percent: 50,
      title_position_y_percent: 90,
      allow_similar_frame_fallback: true,
      similar_frame_fallback_threshold: 18,
    };
    expect(fixedRequest).toMatchObject(fixedBaseline);
    expect(batchCreateBodies(calls)[0].options).toMatchObject({
      frame_count: 18,
    });

    fireEvent.click(batch.getByLabelText("随机标题格式"));
    expect(batch.getByLabelText("随机标题格式")).toBeChecked();
    fireEvent.click(batch.getByRole("button", { name: "生成批量元数据" }));
    fireEvent.click(batch.getByRole("button", { name: "提交批量预览任务" }));
    await waitFor(() => expect(batchCreateCoverSettings(calls)).toHaveLength(2));

    const randomRequest = batchCreateCoverSettings(calls)[1];
    expect(randomRequest.template).toBe("tangxin_vlog");
    expect(["smiley_sans", "zcool_qingke_huangyou", "zcool_kuaile"]).toContain(
      randomRequest.title_font_id,
    );
    expect({
      title_font_id: randomRequest.title_font_id,
      title_font_size: randomRequest.title_font_size,
      title_fill_color: randomRequest.title_fill_color,
      title_stroke_color: randomRequest.title_stroke_color,
      title_stroke_width: randomRequest.title_stroke_width,
      title_effect: randomRequest.title_effect,
      title_angle_degrees: randomRequest.title_angle_degrees,
      title_position_x_percent: randomRequest.title_position_x_percent,
      title_position_y_percent: randomRequest.title_position_y_percent,
      allow_similar_frame_fallback: randomRequest.allow_similar_frame_fallback,
      similar_frame_fallback_threshold: randomRequest.similar_frame_fallback_threshold,
    }).not.toEqual({
      title_font_id: fixedBaseline.title_font_id,
      title_font_size: fixedBaseline.title_font_size,
      title_fill_color: fixedBaseline.title_fill_color,
      title_stroke_color: fixedBaseline.title_stroke_color,
      title_stroke_width: fixedBaseline.title_stroke_width,
      title_effect: fixedBaseline.title_effect,
      title_angle_degrees: fixedBaseline.title_angle_degrees,
      title_position_x_percent: fixedBaseline.title_position_x_percent,
      title_position_y_percent: fixedBaseline.title_position_y_percent,
      allow_similar_frame_fallback: fixedBaseline.allow_similar_frame_fallback,
      similar_frame_fallback_threshold: fixedBaseline.similar_frame_fallback_threshold,
    });
    expect(randomRequest).toMatchObject({
      allow_similar_frame_fallback: true,
      similar_frame_fallback_threshold: 18,
    });
  });

  it("keeps fixed batch cover baseline in compact summaries when random title format is disabled", async () => {
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

    fireEvent.click(batch.getByRole("button", { name: "生成批量元数据" }));
    await waitFor(() => expect(batch.getByRole("heading", { name: "已生成的批量元数据" })).toBeTruthy());
    expect(batch.getAllByText(/TangXin Vlog/).length).toBeGreaterThan(1);
    expect(batch.getAllByText(/LXGW WenKai/).length).toBeGreaterThan(1);
    expect(batch.getAllByText(/80px/).length).toBeGreaterThan(1);
    expect(batch.getAllByText(/#808080 -> #808080/).length).toBeGreaterThan(1);
    expect(batch.getAllByText(/\+10 度 \/ X \+4 Y -6/).length).toBeGreaterThan(1);
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
        path: "/api/local-metadata/batches",
        response: (call) =>
          batchReadFromCreateRequest(call.body, {
            batchId: "batch-preview",
            status: "completed_with_errors",
            itemStatuses: ["succeeded", "failed", "succeeded"],
            itemErrors: [null, "Beta screenshots failed", null],
          }),
      },
      {
        method: "POST",
        path: "/api/local-metadata/batches/batch-preview/execute",
        response: () =>
          batchReadFromCreateRequest(batchCreateBodies(calls)[0], {
            batchId: "batch-preview",
            status: "completed_with_errors",
            itemStatuses: ["executed", "failed", "executed"],
            itemErrors: [null, "Beta screenshots failed", null],
            executed: true,
          }),
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
      target: { value: "move" },
    });
    fireEvent.change(batch.getByLabelText("批量并发数"), {
      target: { value: "2" },
    });
    fireEvent.click(batch.getByRole("button", { name: "生成批量元数据" }));
    await waitFor(() => expect(batch.getByRole("heading", { name: "已生成的批量元数据" })).toBeTruthy());

    const generateButton = batch.getByRole("button", {
      name: "提交批量预览任务",
    });
    fireEvent.click(generateButton);

    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "批量生成摘要" }),
      ).toHaveTextContent("预览可用 2 个，失败 1 个"),
    );
    expect(screen.getByText("失败：Beta screenshots failed")).toBeTruthy();
    expect(screen.getAllByText("计划 plan-alpha-scene").length).toBeGreaterThan(0);
    expect(screen.getAllByText("计划 plan-gamma-scene").length).toBeGreaterThan(0);
    expect(screen.queryByText("计划 plan-beta-scene")).toBeNull();
    expect(screen.getAllByText("已生成").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("生成失败")).toBeTruthy();
    expect(batch.getByText("已选择 3")).toBeTruthy();
    expect(batch.getByText("可执行 2")).toBeTruthy();
    expect(batch.getByText("失败 1")).toBeTruthy();
    expect(batch.getByText(/当前模式会改变原始文件位置或内容/)).toBeTruthy();

    const filters = within(batch.getByRole("group", { name: "批量预览筛选" }));

    fireEvent.click(filters.getByRole("button", { name: /需处理/ }));
    let outputTable = within(batch.getByRole("table", { name: "批量预览结果" }));
    expect(outputTable.getByText("Beta.Scene.mkv")).toBeTruthy();
    expect(outputTable.queryByText("Alpha.Scene.mp4")).toBeNull();
    expect(outputTable.queryByText("Gamma.Scene.mp4")).toBeNull();

    fireEvent.click(filters.getByRole("button", { name: /可执行/ }));
    outputTable = within(batch.getByRole("table", { name: "批量预览结果" }));
    expect(outputTable.getByText("Alpha.Scene.mp4")).toBeTruthy();
    expect(outputTable.getByText("Gamma.Scene.mp4")).toBeTruthy();
    expect(outputTable.queryByText("Beta.Scene.mkv")).toBeNull();

    fireEvent.click(filters.getByRole("button", { name: /全部/ }));
    outputTable = within(batch.getByRole("table", { name: "批量预览结果" }));
    expect(outputTable.getByText("Alpha.Scene.mp4")).toBeTruthy();
    expect(outputTable.getByText("Beta.Scene.mkv")).toBeTruthy();
    expect(outputTable.getByText("Gamma.Scene.mp4")).toBeTruthy();

    expect(batchCreateBodies(calls)).toHaveLength(1);
    expect(batchCreateBodies(calls)[0]).toMatchObject({
      options: { mode: "move", concurrency: 2 },
      items: [{ video_path: "/media/incoming/Alpha.Scene.mp4" }, {}, {}],
    });
    expect(
      calls.some((call) => call.url.includes("/plans/")),
    ).toBe(false);

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(
      batch.getByRole("button", {
        name: "执行全部可执行计划",
      }),
    );
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("移动"));
    await waitFor(() =>
      expect(screen.getAllByText("整理完成").length).toBeGreaterThanOrEqual(2),
    );
    expect(
      calls.filter((call) => call.url === "/api/local-metadata/batches/batch-preview/execute"),
    ).toHaveLength(1);
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
          default_plot: "Frame Source",
          default_tags: ["{actors}", "{studio}", "{resolution}"],
          default_genres: ["{actors}", "{studio}", "{resolution}"],
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
    expect(screen.getByText(/默认选中前 9 张/)).toBeTruthy();
    expect(screen.getByText(/0 居中/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "分析并生成截图" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "分析" })).toBeNull();
    expect(screen.queryByRole("button", { name: "生成截图" })).toBeNull();

    fireEvent.change(screen.getByLabelText("视频路径"), {
      target: { value: "/media/incoming/Frame.Source.mp4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析并生成截图" }));
    await waitFor(() =>
      expect(screen.getByLabelText("标题 (title)")).toHaveValue("Frame Source"),
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
    expect(screen.getByLabelText("相似帧兜底")).toBeChecked();
    expect(screen.getByLabelText("兜底阈值")).toHaveValue(15);

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
    expect(screen.getByText(/已选择 9 张，至少需要 9 张/)).toBeTruthy();
    expect(coverButton).not.toBeDisabled();
    expect(resetFramesButton).toBeDisabled();

    fireEvent.click(firstFrame);
    expect(screen.getByText(/已选择 8 张，至少需要 9 张/)).toBeTruthy();
    expect(coverButton).toBeDisabled();
    expect(resetFramesButton).not.toBeDisabled();

    fireEvent.click(resetFramesButton);
    expect(screen.getByText(/已选择 9 张，至少需要 9 张/)).toBeTruthy();
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
    fireEvent.click(screen.getByLabelText("相似帧兜底"));
    fireEvent.change(screen.getByLabelText("兜底阈值"), {
      target: { value: "20" },
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
      allow_similar_frame_fallback: false,
      similar_frame_fallback_threshold: 20,
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

    fireEvent.change(screen.getByLabelText("标题 (title)"), {
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
          default_plot: "Many Frames",
          default_tags: ["{actors}", "{studio}", "{resolution}"],
          default_genres: ["{actors}", "{studio}", "{resolution}"],
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
    expect(screen.getByText(/已选择 9 张，至少需要 9 张/)).toBeTruthy();
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
  return {
    video_path: videoPath,
    cleaned_title: title,
    default_organize_filename: title,
    default_plot: title,
    default_tags: ["{actors}", "{studio}", "{resolution}"],
    default_genres: ["{actors}", "{studio}", "{resolution}"],
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

function coverPreviewRequestBodies(
  calls: { method: string; url: string; body: unknown }[],
): Record<string, unknown>[] {
  return calls
    .filter(
      (call) =>
        call.method === "POST" && call.url === "/api/local-metadata/cover-preview",
    )
    .map((call) => call.body as Record<string, unknown>);
}

function batchCreateBodies(
  calls: { method: string; url: string; body: unknown }[],
): Record<string, unknown>[] {
  return calls
    .filter(
      (call) =>
        call.method === "POST" && call.url === "/api/local-metadata/batches",
    )
    .map((call) => call.body as Record<string, unknown>);
}

function batchCreateCoverSettings(
  calls: { method: string; url: string; body: unknown }[],
): LocalBatchCoverSettings[] {
  return batchCreateBodies(calls).flatMap((body) => {
    const items = Array.isArray(body.items) ? body.items : [];
    return items.map((item) => (item as { cover_settings: LocalBatchCoverSettings }).cover_settings);
  });
}

function batchReadFromCreateRequest(
  body: unknown,
  options: {
    batchId?: string;
    status?: LocalMetadataBatchStatus;
    itemStatuses?: Array<"pending" | "running" | "succeeded" | "failed" | "executing" | "executed" | "execute_failed" | "cancelled">;
    itemErrors?: Array<string | null>;
    executed?: boolean;
  } = {},
): LocalMetadataBatchRead {
  const request = body as {
    options: LocalMetadataBatchRead["options"];
    items: Array<{
      video_path: string;
      filename: string | null;
      metadata: LocalMetadataDraft;
      cover_settings: LocalBatchCoverSettings;
    }>;
  };
  const now = "2026-07-31T00:00:00";
  const itemStatuses = options.itemStatuses ?? request.items.map(() => "succeeded" as const);
  const items = request.items.map((item, index) => {
    const status = itemStatuses[index] ?? "succeeded";
    return batchItemReadFromCreateItem({
      item,
      index,
      status,
      error: options.itemErrors?.[index] ?? null,
      executed: options.executed,
      now,
    });
  });
  const failedCount = items.filter((item) => item.status === "failed").length;
  const executeFailedCount = items.filter((item) => item.status === "execute_failed").length;
  return {
    batch_id: options.batchId ?? "batch-preview",
    status: options.status ?? (failedCount || executeFailedCount ? "completed_with_errors" : "completed"),
    options: request.options,
    total_count: items.length,
    pending_count: items.filter((item) => item.status === "pending").length,
    running_count: items.filter((item) => item.status === "running" || item.status === "executing").length,
    succeeded_count: items.filter((item) => ["succeeded", "executing", "executed"].includes(item.status)).length,
    failed_count: failedCount,
    executable_count: items.filter((item) => item.status === "succeeded" && item.plan_preview?.plan.mode !== "preview").length,
    executed_count: items.filter((item) => item.status === "executed").length,
    execute_failed_count: executeFailedCount,
    created_at: now,
    updated_at: now,
    items,
  };
}

function batchItemReadFromCreateItem({
  item,
  index,
  status,
  error,
  executed,
  now,
}: {
  item: {
    video_path: string;
    filename: string | null;
    metadata: LocalMetadataDraft;
    cover_settings: LocalBatchCoverSettings;
  };
  index: number;
  status: "pending" | "running" | "succeeded" | "failed" | "executing" | "executed" | "execute_failed" | "cancelled";
  error: string | null;
  executed?: boolean;
  now: string;
}): LocalMetadataBatchRead["items"][number] {
  const stem = slugFromPath(item.video_path);
  const planId = `plan-${stem}`;
  const hasPreview = ["succeeded", "executing", "executed", "execute_failed"].includes(status);
  return {
    item_id: index + 1,
    video_path: item.video_path,
    filename: item.filename ?? item.video_path.split(/[\\/]/).pop() ?? item.video_path,
    draft: item.metadata,
    cover_settings: item.cover_settings,
    status,
    error,
    logs: error
      ? [{ tone: "danger", message: `失败：${error}`, created_at: now }]
      : hasPreview
        ? [{ tone: "success", message: `NFO 与整理计划已生成，计划 ${planId}`, created_at: now }]
        : [],
    frames: hasPreview
      ? Array.from({ length: 9 }, (_, frameIndex) =>
          cachedAssetFixture({
            id: `frames/${stem}-${frameIndex + 1}.jpg`,
            url: `/api/local-metadata/cache/frames/${stem}-${frameIndex + 1}.jpg`,
            time_seconds: (frameIndex + 1) * 20,
          }),
        )
      : [],
    selected_frame_ids: hasPreview
      ? Array.from({ length: 9 }, (_, frameIndex) => `frames/${stem}-${frameIndex + 1}.jpg`)
      : [],
    cover_preview: hasPreview
      ? {
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
          template: item.cover_settings.template,
          title_font_id: item.cover_settings.title_font_id ?? "source_han_sans",
          selected_frame_ids: Array.from({ length: 9 }, (_, frameIndex) => `frames/${stem}-${frameIndex + 1}.jpg`),
          warnings: [],
        }
      : null,
    plan_id: hasPreview ? planId : null,
    plan_preview: hasPreview
      ? {
          plan_id: planId,
          metadata: { title: item.metadata.title },
          materialized_assets: [],
          nfo_xml: `<movie><title>${item.metadata.title}</title></movie>`,
          plan: operationPlanFixture({
            plan_id: planId,
            mode: "copy",
            targetStem: item.metadata.organize_filename ?? item.metadata.title,
          }),
        }
      : null,
    execute_result: executed && status === "executed" ? { plan_id: planId, job_id: null, state: "completed" } : null,
    created_at: now,
    updated_at: now,
  };
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
  overrides: Partial<{
    plan_id: string;
    mode: string;
    targetDirectory: string;
    targetStem: string;
  }> = {},
) {
  const mode = overrides.mode ?? "preview";
  const targetDirectory =
    overrides.targetDirectory ?? "/media/organized/Metadata Title";
  const targetStem = overrides.targetStem ?? "Metadata Title";
  return {
    plan_id: overrides.plan_id ?? "plan-local",
    version: 1,
    job_id: null,
    mode,
    destination_root: "/media/organized",
    target_directory: targetDirectory,
    source_snapshot: [],
    materialized_asset_cache_paths: [],
    steps: [
      operationStepFixture({
        step_id: "step-media",
        operation: mode,
        category: "media",
        source_path: "/media/incoming/Metadata.Title.mp4",
        target_path: `${targetDirectory}/${targetStem}.mp4`,
      }),
      operationStepFixture({
        step_id: "step-nfo",
        operation: "write_generated",
        category: "generated_artifact",
        source_path: null,
        target_path: `${targetDirectory}/${targetStem}.nfo`,
        generated_artifact: true,
      }),
    ],
    conflicts: [],
    safety_warnings: [],
    created_at: "2026-07-27T00:00:00",
  };
}

function operationStepFixture(
  overrides: Partial<{
    step_id: string;
    operation: string;
    category: string;
    source_path: string | null;
    target_path: string;
    generated_artifact: boolean;
  }> = {},
) {
  const targetPath =
    overrides.target_path ?? "/media/organized/Metadata Title/Metadata Title.mp4";
  return {
    step_id: overrides.step_id ?? "step-media",
    operation: overrides.operation ?? "preview",
    category: overrides.category ?? "media",
    source_path: overrides.source_path ?? "/media/incoming/Metadata.Title.mp4",
    target_path: targetPath,
    temp_parent_path: "/media/organized/.xona-tmp",
    expected_size_bytes: null,
    mtime_ns: null,
    sha256: null,
    sidecar: false,
    materialized_asset: false,
    generated_artifact: overrides.generated_artifact ?? false,
    actor_output: false,
    destructive: false,
    allow_existing_generated_replacement: false,
    metadata: {},
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
