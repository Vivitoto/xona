import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ManualOrganizerPage } from "./ManualOrganizerPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ManualOrganizerPage", () => {
  it("supports browse, scan, search, select, preview, and execute after preview", async () => {
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
          accepted: false,
          reasons: [
            "destination_collision",
            "unresolved_multipart",
            "incomplete_metadata",
            "unsafe_path",
            "strict_assets_missing",
          ],
          selected_candidate: {
            candidate_id: 3,
            source: "xchina",
            source_candidate_id: "XC-001",
            title: "Sample Work",
            image_url: null,
            actors: ["Actor One"],
            studio: "Studio One",
            series: "Series One",
            release_date: "2026-01-02",
            url: "https://xchina.example.test/videos/xc-001.html",
            confidence_score: 96,
            score_breakdown: { title: 80, actors: 16 },
          },
          metadata_record_id: 5,
          metadata: { title: "Sample Work" },
        },
      },
      {
        method: "POST",
        path: "/api/manual/jobs/7/preview",
        response: {
          job_id: 7,
          plan_id: "plan-1",
          metadata: { title: "Sample Work" },
          materialized_assets: [{ path: "/config/assets/poster.jpg" }],
          missing_assets: [{ kind: "fanart" }],
          plan: operationPlanFixture(),
        },
      },
      {
        method: "POST",
        path: "/api/manual/plans/plan-1/execute",
        response: { plan_id: "plan-1", job_id: 7, state: "completed" },
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
    expect(screen.getByText("Actor One")).toBeTruthy();
    expect(screen.getByText("title: 80")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "选择候选项" }));
    expect(await screen.findByText("destination_collision")).toBeTruthy();
    expect(screen.getByText("unresolved_multipart")).toBeTruthy();
    expect(screen.getByText("incomplete_metadata")).toBeTruthy();
    expect(screen.getByText("unsafe_path")).toBeTruthy();
    expect(screen.getByText("strict_assets_missing")).toBeTruthy();

    expect(screen.getByRole("button", { name: "执行已批准预览" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/目标目录/i), {
      target: { value: "/media/organized" },
    });
    fireEvent.click(screen.getByRole("button", { name: "预览整理计划" }));
    expect(await screen.findByText(/copy \/media\/incoming\/Sample.Work.mkv/)).toBeTruthy();
    expect(screen.getByText("/config/assets/poster.jpg")).toBeTruthy();
    expect(screen.getByText("fanart")).toBeTruthy();
    expect(
      screen.getAllByText("/media/organized/.actors/Actor One/folder.jpg").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("/media/organized/Studio One/Sample Work/movie.nfo").length,
    ).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "执行已批准预览" }));
    expect(await screen.findByText(/计划 plan-1 状态为 completed/)).toBeTruthy();

    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/manual/plans/plan-1/execute",
      ),
    ).toBe(true);
    const executeCall = calls.find((call) =>
      call.url.endsWith("/api/manual/plans/plan-1/execute"),
    );
    expect((executeCall?.body as { approved: boolean }).approved).toBe(true);
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

function operationPlanFixture() {
  return {
    plan_id: "plan-1",
    version: 1,
    job_id: 7,
    mode: "copy",
    destination_root: "/media/organized",
    target_directory: "/media/organized/Studio One/Sample Work",
    source_snapshot: [],
    materialized_asset_cache_paths: ["/config/assets/poster.jpg"],
    conflicts: [
      {
        target_path: "/media/organized/Studio One/Sample Work/Sample Work.mkv",
        reason: "destination_collision",
        source_path: null,
        allowed: false,
      },
    ],
    safety_warnings: [
      {
        code: "strict_assets_missing",
        message: "Fanart is missing",
        path: "/config/assets/fanart.jpg",
      },
    ],
    created_at: "2026-07-23T00:00:00Z",
    steps: [
      {
        step_id: "media-1",
        operation: "copy",
        category: "media",
        source_path: "/media/incoming/Sample.Work.mkv",
        target_path: "/media/organized/Studio One/Sample Work/Sample Work.mkv",
        temp_parent_path: "/media/organized/.xona-tmp",
        expected_size_bytes: 4,
        mtime_ns: null,
        sha256: null,
        sidecar: false,
        materialized_asset: false,
        generated_artifact: false,
        actor_output: false,
        destructive: false,
        allow_existing_generated_replacement: false,
        metadata: {},
      },
      {
        step_id: "nfo-1",
        operation: "write_generated",
        category: "generated_artifact",
        source_path: null,
        target_path: "/media/organized/Studio One/Sample Work/movie.nfo",
        temp_parent_path: "/media/organized/.xona-tmp",
        expected_size_bytes: 20,
        mtime_ns: null,
        sha256: null,
        sidecar: true,
        materialized_asset: false,
        generated_artifact: true,
        actor_output: false,
        destructive: false,
        allow_existing_generated_replacement: false,
        metadata: {},
      },
      {
        step_id: "actor-1",
        operation: "copy",
        category: "actor_output",
        source_path: "/config/actor-cache/actor-one.jpg",
        target_path: "/media/organized/.actors/Actor One/folder.jpg",
        temp_parent_path: "/media/organized/.xona-tmp",
        expected_size_bytes: 20,
        mtime_ns: null,
        sha256: null,
        sidecar: false,
        materialized_asset: true,
        generated_artifact: false,
        actor_output: true,
        destructive: false,
        allow_existing_generated_replacement: false,
        metadata: {},
      },
    ],
  };
}
