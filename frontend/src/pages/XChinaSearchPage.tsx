import { FormEvent, useMemo, useState } from "react";
import { SearchCheck } from "lucide-react";

import { apiFetch } from "../api/client";
import type {
  XChinaDetailResponse,
  XChinaMetadataRecord,
  XChinaSearchCandidate,
  XChinaSearchResponse,
} from "../api/types";
import { FormField, Section } from "../components/FormField";
import { useImageSafetyMode } from "../components/ImageSafetyMode";
import { proxiedImageUrl } from "../utils/imageProxy";

type LoadState = "idle" | "loading" | "success" | "error";

const XCHINA_RESULT_PAGE_SIZES = [6, 10, 20] as const;
const DEFAULT_XCHINA_RESULT_PAGE_SIZE = 6;

export function XChinaSearchPage() {
  const [query, setQuery] = useState("");
  const [detailUrl, setDetailUrl] = useState("");
  const [candidates, setCandidates] = useState<XChinaSearchCandidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] =
    useState<XChinaSearchCandidate | null>(null);
  const [detail, setDetail] = useState<XChinaDetailResponse | null>(null);
  const [searchState, setSearchState] = useState<LoadState>("idle");
  const [detailState, setDetailState] = useState<LoadState>("idle");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [resultPageSize, setResultPageSize] = useState(
    DEFAULT_XCHINA_RESULT_PAGE_SIZE,
  );
  const [resultPage, setResultPage] = useState(1);

  const selectedMetadata = detail?.metadata ?? null;
  const totalResultPages = Math.max(1, Math.ceil(candidates.length / resultPageSize));
  const visibleResultPage = Math.min(resultPage, totalResultPages);
  const pageStartIndex = candidates.length ? (visibleResultPage - 1) * resultPageSize : 0;
  const pagedCandidates = useMemo(
    () => candidates.slice(pageStartIndex, pageStartIndex + resultPageSize),
    [candidates, pageStartIndex, resultPageSize],
  );
  const resultCountLabel = useMemo(() => {
    if (searchState === "idle") {
      return "输入关键词后开始搜索。";
    }
    if (searchState === "loading") {
      return "正在搜索 XChina。";
    }
    if (searchState === "error") {
      return error || "搜索失败。";
    }
    return candidates.length
      ? `找到 ${candidates.length} 个元数据来源。`
      : "没有找到匹配来源。";
  }, [candidates.length, error, searchState]);

  async function search(event?: FormEvent) {
    event?.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setError("请输入搜索关键词。");
      setSearchState("error");
      return;
    }
    setSearchState("loading");
    setError("");
    setFeedback("");
    setCandidates([]);
    setSelectedCandidate(null);
    setDetail(null);
    setResultPage(1);
    try {
      const response = await apiFetch<XChinaSearchResponse>("/api/xchina/search", {
        method: "POST",
        body: { query: trimmed },
      });
      setQuery(response.normalized_query || response.query);
      setCandidates(response.candidates);
      setSearchState("success");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "搜索失败";
      setError(message);
      setSearchState("error");
    }
  }

  async function fetchDetailFromUrl(event?: FormEvent) {
    event?.preventDefault();
    const sourceUrl = detailUrl.trim();
    if (!sourceUrl) {
      setError("请输入详情 URL。");
      setDetailState("error");
      return;
    }
    await fetchDetail(sourceUrl, null);
  }

  async function fetchCandidateDetail(candidate: XChinaSearchCandidate) {
    setSelectedCandidate(candidate);
    setDetailUrl(candidate.url);
    await fetchDetail(candidate.url, candidate);
  }

  async function fetchDetail(
    sourceUrl: string,
    candidate: XChinaSearchCandidate | null,
  ) {
    setDetailState("loading");
    setError("");
    setFeedback("");
    setDetail(null);
    setDetailUrl(sourceUrl);
    try {
      const response = await apiFetch<XChinaDetailResponse>("/api/xchina/detail", {
        method: "POST",
        body: { source_url: sourceUrl },
      });
      setDetail(response);
      setSelectedCandidate(candidate);
      setDetailUrl(response.source_url);
      setDetailState("success");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "详情获取失败";
      setError(message);
      setDetailState("error");
    }
  }

  function updateResultPageSize(value: string) {
    const nextPageSize = Number(value);
    setResultPageSize(
      XCHINA_RESULT_PAGE_SIZES.includes(
        nextPageSize as (typeof XCHINA_RESULT_PAGE_SIZES)[number],
      )
        ? nextPageSize
        : DEFAULT_XCHINA_RESULT_PAGE_SIZE,
    );
    setResultPage(1);
  }

  async function copyCandidateSourceLink(candidate: XChinaSearchCandidate) {
    setError("");
    setFeedback("");
    try {
      await copyText(candidate.url);
      setFeedback(`已复制来源链接：${candidate.url}`);
    } catch {
      setError(`复制失败，请手动复制：${candidate.url}`);
    }
  }

  function applyToLocalMetadata() {
    if (!selectedMetadata) {
      return;
    }
    localStorage.setItem(
      "xona:xchina-metadata-handoff",
      JSON.stringify(selectedMetadata),
    );
    setFeedback("已暂存，可在本地元数据生成中接入。");
  }

  return (
    <div className="page-stack xchina-search-page">
      <Section title="XChina 元数据搜索">
        <div className="xchina-search-controls">
          <form className="manual-search-row" onSubmit={search}>
            <FormField label="搜索关键词">
              <input
                placeholder="标题、番号、演员或系列"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </FormField>
            <button disabled={searchState === "loading"} type="submit">
              {searchState === "loading" ? "搜索中..." : "搜索"}
            </button>
          </form>

          <form className="manual-detail-url" onSubmit={fetchDetailFromUrl}>
            <FormField label="详情 URL">
              <input
                placeholder="https://www.xchina.co/videos/example.html"
                value={detailUrl}
                onChange={(event) => setDetailUrl(event.target.value)}
              />
            </FormField>
            <button disabled={detailState === "loading"} type="submit">
              {detailState === "loading" ? "获取中..." : "获取详情"}
            </button>
          </form>
        </div>
      </Section>

      <div className="xchina-results-layout">
        <Section title="搜索结果">
          <div className={`search-feedback is-${stateTone(searchState)}`} role="status">
            <strong>{resultCountLabel}</strong>
          </div>
          {candidates.length ? (
            <>
              <div className="xchina-results-toolbar">
                <span>
                  第 {visibleResultPage} / {totalResultPages} 页 · 显示 {pageStartIndex + 1}-
                  {Math.min(pageStartIndex + resultPageSize, candidates.length)} / {candidates.length}
                </span>
                <label>
                  每页
                  <select
                    aria-label="搜索结果每页数量"
                    value={resultPageSize}
                    onChange={(event) => updateResultPageSize(event.target.value)}
                  >
                    {XCHINA_RESULT_PAGE_SIZES.map((pageSize) => (
                      <option key={pageSize} value={pageSize}>
                        {pageSize} 条
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="candidate-grid xchina-candidate-grid">
                {pagedCandidates.map((candidate) => (
                  <XChinaResultCard
                    key={`${candidate.source}:${candidate.source_candidate_id}:${candidate.url}`}
                    candidate={candidate}
                    selected={candidate.url === selectedCandidate?.url}
                    onCopySource={copyCandidateSourceLink}
                    onDetail={fetchCandidateDetail}
                  />
                ))}
              </div>
              <div className="xchina-results-pagination" aria-label="搜索结果分页">
                <button
                  type="button"
                  disabled={visibleResultPage <= 1}
                  onClick={() => setResultPage((page) => Math.max(1, page - 1))}
                >
                  上一页
                </button>
                <span>
                  {visibleResultPage} / {totalResultPages}
                </span>
                <button
                  type="button"
                  disabled={visibleResultPage >= totalResultPages}
                  onClick={() =>
                    setResultPage((page) => Math.min(totalResultPages, page + 1))
                  }
                >
                  下一页
                </button>
              </div>
            </>
          ) : null}
        </Section>

        <Section title="详情元数据">
          {detail ? (
            <XChinaDetailPreview
              detail={detail}
              onApplyToLocalMetadata={applyToLocalMetadata}
            />
          ) : (
            <div className="empty-state xchina-empty-state">
              <span className="empty-state-icon" aria-hidden="true">
                <SearchCheck size={20} strokeWidth={2.2} />
              </span>
              <strong>等待详情</strong>
              <span>从搜索结果选择来源，或直接粘贴详情 URL。</span>
            </div>
          )}
          {feedback ? <p className="status">{feedback}</p> : null}
          {error ? <p className="status error">{error}</p> : null}
        </Section>
      </div>
    </div>
  );
}

function XChinaResultCard({
  candidate,
  selected,
  onCopySource,
  onDetail,
}: {
  candidate: XChinaSearchCandidate;
  selected: boolean;
  onCopySource: (candidate: XChinaSearchCandidate) => void;
  onDetail: (candidate: XChinaSearchCandidate) => void;
}) {
  const { imageSafetyModeEnabled } = useImageSafetyMode();
  const imageSrc = proxiedImageUrl(candidate.image_url, "xchina");
  const safetyLabel = imageSafetyModeEnabled
    ? `${candidate.title} 图片，安全模式已模糊，悬停、聚焦或轻点可临时查看`
    : `${candidate.title} 图片`;

  return (
    <article
      aria-label={candidate.title}
      className={`candidate-card xchina-source-card${selected ? " is-selected" : ""}`}
    >
      <div className="candidate-image">
        {imageSrc ? (
          <img
            alt={`${candidate.title} 图片`}
            aria-label={safetyLabel}
            className={`safety-image${imageSafetyModeEnabled ? " is-blurred" : ""}`}
            data-image-safety={imageSafetyModeEnabled ? "blurred" : "visible"}
            src={imageSrc}
            tabIndex={imageSafetyModeEnabled ? 0 : undefined}
            title={
              imageSafetyModeEnabled
                ? "安全模式已开启，悬停、聚焦或轻点图片可临时查看。"
                : "安全模式已关闭。"
            }
          />
        ) : (
          <span aria-label={`${candidate.title} 缺少图片`} role="img">
            无图片
          </span>
        )}
      </div>
      <div className="candidate-body">
        <div className="candidate-heading">
          <div className="candidate-title-block">
            <div className="candidate-badges" aria-label="来源信息">
              <span>{candidate.source.toUpperCase()}</span>
              <span>ID {candidate.source_candidate_id}</span>
            </div>
            <h3>{candidate.title}</h3>
          </div>
        </div>
        <dl className="metadata-list compact">
          <div>
            <dt>演员</dt>
            <dd>{formatList(candidate.actors, "未知")}</dd>
          </div>
          <div>
            <dt>制作方</dt>
            <dd>{candidate.studio || "未知"}</dd>
          </div>
          <div>
            <dt>系列</dt>
            <dd>{candidate.series || "无"}</dd>
          </div>
          <div>
            <dt>日期</dt>
            <dd>{candidate.release_date || "未知"}</dd>
          </div>
        </dl>
        <div className="candidate-footer">
          <a
            aria-label={`打开 ${candidate.title} 的来源页面`}
            className="candidate-source-link"
            href={candidate.url}
            rel="noreferrer"
            target="_blank"
          >
            打开来源
          </a>
          <button
            className="secondary"
            type="button"
            onClick={() => onCopySource(candidate)}
          >
            复制来源链接
          </button>
          <button
            className="candidate-select-button"
            type="button"
            onClick={() => onDetail(candidate)}
          >
            查看详情
          </button>
        </div>
      </div>
    </article>
  );
}

function XChinaDetailPreview({
  detail,
  onApplyToLocalMetadata,
}: {
  detail: XChinaDetailResponse;
  onApplyToLocalMetadata: () => void;
}) {
  const metadata = detail.metadata;
  const { imageSafetyModeEnabled } = useImageSafetyMode();
  const imageSrc = proxiedImageUrl(metadata.assets.poster_url, "xchina");
  const title = metadata.title || detail.detail.title;
  const safetyLabel = imageSafetyModeEnabled
    ? `${title} 详情图片，安全模式已模糊，悬停、聚焦或轻点可临时查看`
    : `${title} 详情图片`;

  return (
    <article className="selected-candidate-detail xchina-detail-preview">
      <div className="selected-candidate-poster">
        {imageSrc ? (
          <img
            alt={`${title} 详情图片`}
            aria-label={safetyLabel}
            className={`safety-image${imageSafetyModeEnabled ? " is-blurred" : ""}`}
            data-image-safety={imageSafetyModeEnabled ? "blurred" : "visible"}
            src={imageSrc}
            tabIndex={imageSafetyModeEnabled ? 0 : undefined}
            title={
              imageSafetyModeEnabled
                ? "安全模式已开启，悬停、聚焦或轻点图片可临时查看。"
                : "安全模式已关闭。"
            }
          />
        ) : (
          <span>暂无图片</span>
        )}
      </div>
      <div className="selected-candidate-main">
        <div className="selected-candidate-title-row">
          <div>
            <div className="candidate-badges" aria-label="详情来源信息">
              <span>{metadata.source.toUpperCase()}</span>
              {metadata.xchina_id ? <span>ID {metadata.xchina_id}</span> : null}
            </div>
            <h3>{title}</h3>
          </div>
          <a
            className="candidate-source-link"
            href={metadata.source_url}
            rel="noreferrer"
            target="_blank"
          >
            打开来源
          </a>
        </div>

        <dl className="metadata-list selected-detail-list">
          <div>
            <dt>原标题</dt>
            <dd>{metadata.original_title || "无"}</dd>
          </div>
          <div>
            <dt>演员</dt>
            <dd>{formatList(metadata.actors.map((actor) => actor.name), "未知")}</dd>
          </div>
          <div>
            <dt>制作方</dt>
            <dd>{metadata.studio || "未知"}</dd>
          </div>
          <div>
            <dt>系列</dt>
            <dd>{metadata.series || "无"}</dd>
          </div>
          <div>
            <dt>日期</dt>
            <dd>{metadata.release_date || "未知"}</dd>
          </div>
          <div>
            <dt>片长</dt>
            <dd>
              {metadata.runtime_minutes ? `${metadata.runtime_minutes} 分钟` : "未知"}
            </dd>
          </div>
        </dl>

        {metadata.plot ? (
          <p className="selected-candidate-plot">{metadata.plot}</p>
        ) : null}
        <div className="selected-candidate-chips">
          {metadata.genres.map((genre) => (
            <span key={`genre:${genre}`}>{genre}</span>
          ))}
          {metadata.tags.map((tag) => (
            <span key={`tag:${tag}`}>{tag}</span>
          ))}
        </div>
        <pre aria-label="元数据 JSON 预览" className="metadata-json-preview">
          {JSON.stringify(metadata, null, 2)}
        </pre>
        <div className="button-row">
          <button type="button" onClick={onApplyToLocalMetadata}>
            应用到本地元数据生成
          </button>
        </div>
      </div>
    </article>
  );
}

function formatList(values: string[], fallback: string): string {
  const visible = values.filter(Boolean);
  return visible.length ? visible.join(", ") : fallback;
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    if (!document.execCommand?.("copy")) {
      throw new Error("copy command unavailable");
    }
  } finally {
    document.body.removeChild(textarea);
  }
}

function stateTone(state: LoadState): string {
  if (state === "loading") {
    return "loading";
  }
  if (state === "success") {
    return "success";
  }
  if (state === "error") {
    return "error";
  }
  return "idle";
}
