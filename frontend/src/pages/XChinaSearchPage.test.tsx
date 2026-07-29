import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { XChinaSearchPage } from "./XChinaSearchPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("XChinaSearchPage", () => {
  it("searches XChina with only a keyword and renders metadata source cards", async () => {
    const { calls } = installFetchMock([
      {
        method: "POST",
        path: "/api/xchina/search",
        response: xchinaSearchFixture(),
      },
      {
        method: "POST",
        path: "/api/xchina/detail",
        response: xchinaDetailFixture(),
      },
    ]);

    render(<XChinaSearchPage />);

    fireEvent.change(screen.getByLabelText("搜索关键词"), {
      target: { value: "Sample Work Alpha" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    const card = await screen.findByRole("article", {
      name: "Sample Work Alpha",
    });
    expect(within(card).getByText("Actor One")).toBeTruthy();
    expect(screen.queryByText(/置信度|confidence/i)).not.toBeInTheDocument();

    const image = within(card).getByRole("img", {
      name: /Sample Work Alpha 图片/,
    });
    expect(image).toHaveAttribute(
      "src",
      "/api/xchina/image-proxy?url=https%3A%2F%2Fimg.xchina.download%2Fthumb.jpg",
    );

    const searchCall = calls.find((call) => call.url === "/api/xchina/search");
    expect(searchCall?.body).toEqual({ query: "Sample Work Alpha" });
    expect(searchCall?.body).not.toHaveProperty("job_id");
    expect(searchCall?.body).not.toHaveProperty("media_path");
    expect(searchCall?.body).not.toHaveProperty("confidence_threshold");

    fireEvent.click(within(card).getByRole("button", { name: "查看详情" }));

    expect(screen.getByLabelText("详情 URL")).toHaveValue(
      "https://xchina.example.test/videos/xc-001.html",
    );

    expect(await screen.findByText("Sample Work Alpha Original")).toBeTruthy();
    expect(screen.getByLabelText("元数据 JSON 预览")).toHaveTextContent("XC-001");

    await waitFor(() => {
      expect(calls.some((call) => call.url === "/api/xchina/detail")).toBe(true);
    });
  });

  it("fetches detail metadata from a direct URL without local video or job fields", async () => {
    const sourceUrl = "https://xchina.example.test/videos/xc-001.html";
    const { calls } = installFetchMock([
      {
        method: "POST",
        path: "/api/xchina/detail",
        response: xchinaDetailFixture(sourceUrl),
      },
    ]);

    render(<XChinaSearchPage />);

    fireEvent.change(screen.getByLabelText("详情 URL"), {
      target: { value: sourceUrl },
    });
    fireEvent.click(screen.getByRole("button", { name: "获取详情" }));

    expect(await screen.findByRole("heading", { name: "Sample Work Alpha" })).toBeTruthy();
    expect(screen.getByText("Sample Work Alpha Original")).toBeTruthy();
    expect(screen.getByLabelText("元数据 JSON 预览")).toHaveTextContent(sourceUrl);
    expect(screen.queryByText(/置信度|confidence/i)).not.toBeInTheDocument();

    const detailCall = calls.find((call) => call.url === "/api/xchina/detail");
    expect(detailCall?.body).toEqual({ source_url: sourceUrl });
    expect(detailCall?.body).not.toHaveProperty("job_id");
    expect(detailCall?.body).not.toHaveProperty("media_path");
    expect(detailCall?.body).not.toHaveProperty("confidence_threshold");
  });

  it("paginates search results and lets users change the page size", async () => {
    installFetchMock([
      {
        method: "POST",
        path: "/api/xchina/search",
        response: xchinaSearchFixture(12),
      },
    ]);

    render(<XChinaSearchPage />);

    fireEvent.change(screen.getByLabelText("搜索关键词"), {
      target: { value: "Sample Work" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    expect(await screen.findByText("Sample Work Alpha 01")).toBeTruthy();
    expect(screen.getByText("Sample Work Alpha 06")).toBeTruthy();
    expect(screen.queryByText("Sample Work Alpha 07")).not.toBeInTheDocument();
    expect(screen.getByLabelText("搜索结果每页数量")).toHaveValue("6");
    expect(screen.getByText(/第 1 \/ 2 页/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(await screen.findByText("Sample Work Alpha 07")).toBeTruthy();
    expect(screen.queryByText("Sample Work Alpha 01")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索结果每页数量"), {
      target: { value: "10" },
    });

    expect(await screen.findByText("Sample Work Alpha 01")).toBeTruthy();
    expect(screen.getByText("Sample Work Alpha 10")).toBeTruthy();
    expect(screen.queryByText("Sample Work Alpha 11")).not.toBeInTheDocument();
    expect(screen.getByText(/第 1 \/ 2 页/)).toBeTruthy();
  });

  it("copies result source links and keeps failed detail URLs visible", async () => {
    const clipboardWriteText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: clipboardWriteText },
    });
    const sourceUrl = "https://xchina.example.test/video/id-XC-001.html";
    installFetchMock([
      {
        method: "POST",
        path: "/api/xchina/search",
        response: xchinaSearchFixture(1, sourceUrl),
      },
      {
        method: "POST",
        path: "/api/xchina/detail",
        response: { detail: "XChina detail URL must be an on-site /video or /videos page" },
        status: 400,
      },
    ]);

    render(<XChinaSearchPage />);

    fireEvent.change(screen.getByLabelText("搜索关键词"), {
      target: { value: "Sample Work Alpha" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    const card = await screen.findByRole("article", { name: "Sample Work Alpha" });

    fireEvent.click(within(card).getByRole("button", { name: "复制来源链接" }));

    await waitFor(() => expect(clipboardWriteText).toHaveBeenCalledWith(sourceUrl));
    expect(screen.getByText(`已复制来源链接：${sourceUrl}`)).toBeTruthy();

    fireEvent.click(within(card).getByRole("button", { name: "查看详情" }));

    expect(screen.getByLabelText("详情 URL")).toHaveValue(sourceUrl);
    expect(await screen.findByText(/on-site \/video or \/videos page/)).toBeTruthy();
  });
});

function xchinaSearchFixture(count = 1, firstUrl?: string) {
  return {
    query: "Sample Work Alpha",
    normalized_query: "Sample Work Alpha",
    candidates: Array.from({ length: count }, (_, index) => {
      const padded = String(index + 1).padStart(2, "0");
      const singleCandidate = count === 1;
      return {
        source: "xchina",
        source_candidate_id: singleCandidate ? "XC-001" : `XC-${padded}`,
        title: singleCandidate ? "Sample Work Alpha" : `Sample Work Alpha ${padded}`,
        image_url: "https://img.xchina.download/thumb.jpg",
        actors: ["Actor One"],
        studio: "Studio One",
        series: "Series One",
        release_date: "2026-01-02",
        url:
          index === 0 && firstUrl
            ? firstUrl
            : singleCandidate
              ? "https://xchina.example.test/videos/xc-001.html"
              : `https://xchina.example.test/videos/xc-${padded}.html`,
      };
    }),
  };
}

function xchinaDetailFixture(sourceUrl = "https://xchina.example.test/videos/xc-001.html") {
  return {
    source_url: sourceUrl,
    detail: {
      source: "xchina",
      source_id: "XC-001",
      source_url: sourceUrl,
      title: "Sample Work Alpha",
      original_title: "Sample Work Alpha Original",
      plot: "Synthetic plot.",
      release_date: "2026-01-02",
      runtime_minutes: 90,
      studio: "Studio One",
      series: "Series One",
      director: "Director One",
      actors: [{ name: "Actor One", source_id: "ACT-001" }],
      genres: ["Drama"],
      tags: ["Tag One"],
      poster: { url: "https://img.xchina.download/poster.jpg", kind: "poster" },
      fanart: { url: "https://img.xchina.download/fanart.jpg", kind: "fanart" },
      backdrops: [],
      trailer: null,
      source_snapshot_eligible: false,
      is_complete: true,
      completeness_flags: [],
    },
    metadata: {
      source: "xchina",
      xchina_id: "XC-001",
      source_url: sourceUrl,
      title: "Sample Work Alpha",
      original_title: "Sample Work Alpha Original",
      sort_title: "Sample Work Alpha",
      plot: "Synthetic plot.",
      outline: "Synthetic plot.",
      release_date: "2026-01-02",
      runtime_minutes: 90,
      studio: "Studio One",
      series: "Series One",
      director: "Director One",
      actors: [{ name: "Actor One", source_id: "ACT-001" }],
      genres: ["Drama"],
      tags: ["Tag One"],
      assets: {
        poster_url: "https://img.xchina.download/poster.jpg",
        fanart_url: "https://img.xchina.download/fanart.jpg",
        backdrop_urls: [],
        thumb_url: null,
        clearlogo_url: null,
        trailer_url: null,
      },
    },
  };
}
