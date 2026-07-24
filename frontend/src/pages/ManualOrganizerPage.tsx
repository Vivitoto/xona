import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  ManualCandidateCard as ManualCandidate,
  ManualExecutePlanResponse,
  ManualJobSummary,
  ManualPreviewResponse,
  ManualScanResponse,
  ManualSearchResponse,
  OrganizationMode,
} from "../api/types";
import { CandidateCard } from "../components/CandidateCard";
import { DirectoryPicker } from "../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { OperationPlanView } from "../components/OperationPlanView";
import { TemplateGuide } from "../components/TemplateGuide";
import { linesToList } from "./settings/settingsForm";

const safetyLabels = [
  ["file_conflict", "文件冲突拒绝"],
  ["unresolved_multipart", "未解决的分段文件"],
  ["incomplete_metadata", "元数据不完整"],
  ["unsafe_path", "不安全路径"],
  ["strict_assets_missing", "严格资源失败"],
] as const;

type SafetyKey = (typeof safetyLabels)[number][0];
type QuerySource = "filename" | "parent" | "custom";
const mediaFilePageSizes = [5, 10, 20] as const;

export function ManualOrganizerPage() {
  const [directory, setDirectory] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [ignorePatterns, setIgnorePatterns] = useState("");
  const [jobs, setJobs] = useState<ManualJobSummary[]>([]);
  const [jobId, setJobId] = useState("");
  const [querySource, setQuerySource] = useState<QuerySource>("filename");
  const [searchQuery, setSearchQuery] = useState("");
  const [candidates, setCandidates] = useState<ManualCandidate[]>([]);
  const [selected, setSelected] = useState<ManualCandidate | null>(null);
  const [detailUrl, setDetailUrl] = useState("");
  const [strictAssets, setStrictAssets] = useState(false);
  const [safety, setSafety] = useState<Record<SafetyKey, boolean>>({
    file_conflict: false,
    unresolved_multipart: false,
    incomplete_metadata: false,
    unsafe_path: false,
    strict_assets_missing: false,
  });
  const [refusalReasons, setRefusalReasons] = useState<string[]>([]);
  const [destinationRoot, setDestinationRoot] = useState("");
  const [mode, setMode] = useState<OrganizationMode>("copy");
  const [folderTemplates, setFolderTemplates] = useState("{studio}\n{title}");
  const [filenameTemplate, setFilenameTemplate] = useState("{xchina_id} - {title}");
  const [assetPolicy, setAssetPolicy] = useState("strict");
  const [includeSourceSnapshot, setIncludeSourceSnapshot] = useState(false);
  const [preview, setPreview] = useState<ManualPreviewResponse | null>(null);
  const [executeResult, setExecuteResult] =
    useState<ManualExecutePlanResponse | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [searchState, setSearchState] = useState<
    "idle" | "searching" | "success" | "error"
  >("idle");
  const [searchFeedback, setSearchFeedback] = useState("");

  const activeJob = useMemo(
    () => jobs.find((job) => String(job.job_id) === jobId) ?? jobs[0] ?? null,
    [jobId, jobs],
  );
  const activeMedia = activeJob?.media_items[0] ?? null;

  useEffect(() => {
    if (!activeJob) {
      return;
    }
    setQuerySource("filename");
    setSearchQuery(defaultQuery(activeJob, "filename"));
    setCandidates([]);
    setSelected(null);
    setRefusalReasons([]);
    setPreview(null);
    setExecuteResult(null);
    setSearchState("idle");
    setSearchFeedback("");
  }, [activeJob?.job_id]);

  async function scan(event?: FormEvent) {
    event?.preventDefault();
    setStatus("正在扫描");
    setError("");
    try {
      const response = await apiFetch<ManualScanResponse>("/api/manual/scan", {
        method: "POST",
        body: {
          directory,
          recursive,
          ignore_patterns: linesToList(ignorePatterns),
        },
      });
      setJobs(response.jobs);
      if (response.jobs[0]) {
        setJobId(String(response.jobs[0].job_id));
        setQuerySource("filename");
        setSearchQuery(defaultQuery(response.jobs[0], "filename"));
      }
      setSearchState("idle");
      setSearchFeedback("");
      setStatus(`已扫描 ${response.scanned_count} 个视频文件`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "扫描失败");
    }
  }

  async function search(nextSource: QuerySource = querySource) {
    const job = activeJob;
    if (!job) {
      setError("请先扫描并选择一个视频文件。");
      setSearchState("error");
      setSearchFeedback("请先扫描并选择一个视频文件。");
      return;
    }
    const query = nextSource === "custom" ? searchQuery : defaultQuery(job, nextSource);
    if (!query.trim()) {
      setError("请输入搜索关键词。");
      setSearchState("error");
      setSearchFeedback("请输入搜索关键词。");
      return;
    }
    setQuerySource(nextSource);
    setSearchQuery(query);
    setSearchState("searching");
    setSearchFeedback(`正在搜索「${query}」…`);
    setStatus("");
    setError("");
    setCandidates([]);
    setSelected(null);
    setPreview(null);
    setExecuteResult(null);
    try {
      const response = await apiFetch<ManualSearchResponse>("/api/manual/search", {
        method: "POST",
        body: {
          job_id: job.job_id,
          query,
          normalized_query: query,
        },
      });
      setJobId(String(response.job_id));
      setSearchQuery(response.normalized_query);
      setCandidates(response.candidates);
      setSearchState("success");
      setSearchFeedback(
        response.candidates.length
          ? `搜索完成：找到 ${response.candidates.length} 个候选结果。`
          : `搜索完成：没有找到候选结果。`,
      );
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "搜索失败";
      setSearchState("error");
      setSearchFeedback(message);
      setError(message);
    }
  }

  async function selectCandidate(candidate: ManualCandidate | null = selected) {
    const activeJobId = activeJob?.job_id;
    if (!activeJobId) {
      setError("请先选择一个视频文件。");
      return;
    }
    setError("");
    setStatus("正在刮削详情并校验");
    try {
      const response = await apiFetch<{
        accepted: boolean;
        reasons: string[];
        selected_candidate: ManualCandidate | null;
      }>(`/api/manual/jobs/${activeJobId}/select-candidate`, {
        method: "POST",
        body: {
          candidate_id: candidate?.candidate_id ?? null,
          source_url: detailUrl || candidate?.url || null,
          strict_assets: strictAssets,
          safety: safetyPayload(),
        },
      });
      setSelected(response.selected_candidate ?? candidate);
      setRefusalReasons(response.reasons);
      setStatus(response.accepted ? "已选择候选结果，可以预览整理计划" : "需要人工复核");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "候选项选择失败");
    }
  }

  async function previewPlan() {
    const activeJobId = activeJob?.job_id;
    if (!activeJobId) {
      setError("预览前需要选择一个视频文件。");
      return;
    }
    setError("");
    setStatus("正在生成整理预览");
    try {
      const response = await apiFetch<ManualPreviewResponse>(
        `/api/manual/jobs/${activeJobId}/preview`,
        {
          method: "POST",
          body: {
            destination_root: destinationRoot,
            mode,
            folder_templates: linesToList(folderTemplates),
            filename_template: filenameTemplate,
            asset_policy: assetPolicy,
            include_source_snapshot: includeSourceSnapshot,
          },
        },
      );
      setPreview(response);
      setStatus("整理预览已生成");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "预览失败");
    }
  }

  async function executePlan() {
    if (!preview) {
      return;
    }
    setError("");
    setStatus("正在执行整理计划");
    try {
      const response = await apiFetch<ManualExecutePlanResponse>(
        `/api/manual/plans/${preview.plan_id}/execute`,
        {
          method: "POST",
          body: {
            approved: true,
            plan_version: preview.plan.version,
          },
        },
      );
      setExecuteResult(response);
      setStatus(`执行状态 ${response.state}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "执行失败");
    }
  }

  function pickJob(job: ManualJobSummary) {
    setJobId(String(job.job_id));
    setQuerySource("filename");
  }

  function safetyPayload(): Record<string, boolean> {
    return {
      file_conflict: safety.file_conflict,
      unresolved_multipart: safety.unresolved_multipart,
      unsafe_path: safety.unsafe_path,
      strict_assets_missing: safety.strict_assets_missing,
    };
  }

  return (
    <div className="page-stack manual-workbench">
      <Section title="扫描目录">
        <form className="manual-scan-bar" onSubmit={scan}>
          <div className="path-field">
            <FormField label="源目录">
              <input
                placeholder="/media/incoming"
                value={directory}
                onChange={(event) => setDirectory(event.target.value)}
              />
            </FormField>
            <DirectoryPicker
              initialPath={directory}
              onSelect={setDirectory}
              title="选择源目录"
            />
          </div>
          <CheckboxField
            checked={recursive}
            label="递归扫描"
            description="包含子目录中的视频文件。"
            onChange={setRecursive}
          />
          <FormField
            description="可选。每行一个 glob，用于跳过样片、系统目录等无关文件。"
            label="忽略模式"
          >
            <textarea
              placeholder={'*.sample.*\n@eaDir/**'}
              value={ignorePatterns}
              onChange={(event) => setIgnorePatterns(event.target.value)}
            />
          </FormField>
          <div className="action-panel">
            <button disabled={!directory} type="submit">
              扫描源目录
            </button>
          </div>
        </form>
      </Section>

      <div className="manual-match-layout">
        <Section title="视频文件">
          <MediaFileList jobs={jobs} activeJobId={activeJob?.job_id ?? null} onPick={pickJob} />
        </Section>

        <Section title="XChina 搜索结果">
          {activeJob ? (
            <div className="match-panel">
              <div className="selected-media-card">
                <span className="badge">当前文件</span>
                <strong>{activeMedia ? fileName(activeMedia.path) : activeJob.media_identity}</strong>
                <small>{activeMedia?.path ?? activeJob.media_identity}</small>
                <small>父目录：{activeMedia ? parentName(activeMedia.path) : "未知"}</small>
              </div>

              <div className="query-toolbar">
                <button className={querySource === "filename" ? "" : "secondary"} disabled={searchState === "searching"} type="button" onClick={() => void search("filename")}>
                  用文件名搜索
                </button>
                <button className={querySource === "parent" ? "" : "secondary"} disabled={searchState === "searching"} type="button" onClick={() => void search("parent")}>
                  用父目录搜索
                </button>
              </div>

              <div className="manual-search-row">
                <FormField label="搜索关键词">
                  <input
                    placeholder="番号、文件名或父目录名"
                    value={searchQuery}
                    onChange={(event) => {
                      setQuerySource("custom");
                      setSearchQuery(event.target.value);
                    }}
                  />
                </FormField>
                <button disabled={searchState === "searching"} type="button" onClick={() => void search("custom")}>
                  {searchState === "searching" ? "搜索中…" : "搜索"}
                </button>
              </div>

              <div className="manual-detail-url">
                <FormField
                  description="搜索不到时可粘贴详情页 URL。"
                  label="详情 URL"
                >
                  <input
                    placeholder="https://www.xchina.co/movie/xxxx"
                    value={detailUrl}
                    onChange={(event) => setDetailUrl(event.target.value)}
                  />
                </FormField>
                <button type="button" onClick={() => void selectCandidate()}>
                  使用 URL 刮削
                </button>
              </div>

              <details className="advanced-options">
                <summary>高级安全选项</summary>
                <div className="safety-grid" aria-label="安全门禁">
                  <CheckboxField
                    checked={strictAssets}
                    label="严格资源"
                    description="要求图片和元数据资源完整。"
                    onChange={setStrictAssets}
                  />
                  {safetyLabels.map(([key, label]) => (
                    <CheckboxField
                      key={key}
                      checked={safety[key]}
                      label={label}
                      onChange={(checked) =>
                        setSafety((current) => ({ ...current, [key]: checked }))
                      }
                    />
                  ))}
                </div>
              </details>

              <div className="candidate-results-panel" aria-label="候选结果">
                <SearchFeedback
                  candidateCount={candidates.length}
                  feedback={searchFeedback}
                  state={searchState}
                />
                {candidates.length ? (
                  <div className="candidate-grid candidate-grid-compact">
                    {candidates.map((candidate) => (
                      <CandidateCard
                        key={candidate.candidate_id}
                        candidate={candidate}
                        selected={candidate.candidate_id === selected?.candidate_id}
                        onSelect={(nextCandidate) => {
                          setSelected(nextCandidate);
                          void selectCandidate(nextCandidate);
                        }}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
              {refusalReasons.length ? (
                <div className="review-reasons" aria-label="复核原因">
                  <strong>需要复核</strong>
                  <ul>
                    {refusalReasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-state">
              <strong>等待扫描</strong>
              <span>选择源目录并扫描后，视频文件会出现在左侧。</span>
            </div>
          )}
        </Section>
      </div>

      <Section title="预览/执行整理">
        <div className="grid four">
          <div className="path-field">
            <FormField label="目标目录">
              <input
                placeholder="/media/organized"
                value={destinationRoot}
                onChange={(event) => setDestinationRoot(event.target.value)}
              />
            </FormField>
            <DirectoryPicker
              initialPath={destinationRoot}
              onSelect={setDestinationRoot}
              title="选择目标目录"
            />
          </div>
          <FormField label="整理模式">
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as OrganizationMode)}
            >
              <option value="preview">只预览</option>
              <option value="copy">复制</option>
              <option value="move">移动</option>
              <option value="hardlink">硬链接</option>
              <option value="symlink">符号链接</option>
              <option value="in_place">原地处理</option>
            </select>
          </FormField>
          <FormField label="资源策略">
            <select
              value={assetPolicy}
              onChange={(event) => setAssetPolicy(event.target.value)}
            >
              <option value="lenient">宽松</option>
              <option value="strict">严格</option>
            </select>
          </FormField>
          <CheckboxField
            checked={includeSourceSnapshot}
            label="包含源快照"
            onChange={setIncludeSourceSnapshot}
          />
        </div>
        <div className="grid two">
          <FormField label="文件夹模板">
            <textarea
              placeholder={'{studio}\n{xchina_id} - {title}'}
              value={folderTemplates}
              onChange={(event) => setFolderTemplates(event.target.value)}
            />
          </FormField>
          <FormField label="文件名模板">
            <input
              placeholder="{xchina_id} - {title}"
              value={filenameTemplate}
              onChange={(event) => setFilenameTemplate(event.target.value)}
            />
          </FormField>
        </div>
        <TemplateGuide />
        <div className="button-row">
          <button disabled={!selected || !destinationRoot} type="button" onClick={previewPlan}>
            预览整理计划
          </button>
          <button disabled={!preview} type="button" onClick={executePlan}>
            执行已批准预览
          </button>
        </div>
        {preview ? (
          <OperationPlanView preview={preview} refusalReasons={refusalReasons} />
        ) : (
          <p className="muted">暂无预览。</p>
        )}
        {executeResult ? (
          <p className="status">
            计划 {executeResult.plan_id} 状态为 {executeResult.state}
          </p>
        ) : null}
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? <p className="status error floating-status">{error}</p> : null}
    </div>
  );
}

function MediaFileList({
  activeJobId,
  jobs,
  onPick,
}: {
  activeJobId: number | null;
  jobs: ManualJobSummary[];
  onPick: (job: ManualJobSummary) => void;
}) {
  const [pageSize, setPageSize] = useState<(typeof mediaFilePageSizes)[number]>(10);
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const visibleJobs = jobs.slice(startIndex, startIndex + pageSize);

  useEffect(() => {
    setPage(1);
  }, [jobs.length, pageSize]);

  if (!jobs.length) {
    return (
      <div className="empty-state">
        <strong>还没有视频文件</strong>
        <span>选择源目录并扫描后，文件会显示在这里。</span>
      </div>
    );
  }

  return (
    <div className="media-file-list" aria-label="扫描到的视频文件">
      <div className="media-file-pagination-summary">
        <span>
          共 {jobs.length} 个视频，显示第 {startIndex + 1}-
          {Math.min(startIndex + pageSize, jobs.length)} 个
        </span>
        <label>
          每页
          <select
            aria-label="每页显示视频数量"
            value={pageSize}
            onChange={(event) =>
              setPageSize(Number(event.target.value) as typeof pageSize)
            }
          >
            {mediaFilePageSizes.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>
      {visibleJobs.map((job) => {
        const item = job.media_items[0];
        const active = job.job_id === activeJobId;
        return (
          <button
            aria-pressed={active}
            className={`media-file-card${active ? " is-active" : ""}`}
            key={job.job_id}
            type="button"
            onClick={() => onPick(job)}
          >
            <span className="media-file-main">
              <strong>{item ? fileName(item.path) : job.media_identity}</strong>
              <small>父目录：{item ? parentName(item.path) : "未知"}</small>
            </span>
            <span className="status-pill">{job.state}</span>
          </button>
        );
      })}
      <div className="media-file-pagination-controls">
        <button
          className="secondary"
          disabled={safePage <= 1}
          type="button"
          onClick={() => setPage((current) => Math.max(1, current - 1))}
        >
          上一页
        </button>
        <span aria-label="当前视频分页">
          {safePage} / {totalPages}
        </span>
        <button
          className="secondary"
          disabled={safePage >= totalPages}
          type="button"
          onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
        >
          下一页
        </button>
      </div>
    </div>
  );
}

function SearchFeedback({
  candidateCount,
  feedback,
  state,
}: {
  candidateCount: number;
  feedback: string;
  state: "idle" | "searching" | "success" | "error";
}) {
  if (state === "idle") {
    return (
      <div className="search-feedback" role="status">
        <strong>等待搜索</strong>
        <span>可用文件名、父目录名，或手动输入关键词搜索 XChina。</span>
      </div>
    );
  }

  if (state === "searching") {
    return (
      <div className="search-feedback is-loading" aria-live="polite" role="status">
        <strong>正在搜索</strong>
        <span>{feedback || "正在连接 XChina，请稍候…"}</span>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="search-feedback is-error" aria-live="assertive" role="alert">
        <strong>搜索失败</strong>
        <span>{feedback || "后台搜索失败，请检查网络或稍后重试。"}</span>
      </div>
    );
  }

  return (
    <div className="search-feedback is-success" aria-live="polite" role="status">
      <strong>{candidateCount ? "搜索完成" : "没有结果"}</strong>
      <span>
        {feedback ||
          (candidateCount
            ? `找到 ${candidateCount} 个候选结果。`
            : "没有找到候选结果，可换关键词或粘贴详情 URL。")}
      </span>
    </div>
  );
}

function defaultQuery(job: ManualJobSummary, source: QuerySource): string {
  const path = job.media_items[0]?.path ?? job.media_identity;
  if (source === "parent") {
    return normalizeQuery(parentName(path));
  }
  if (source === "custom") {
    return normalizeQuery(job.media_identity);
  }
  return normalizeQuery(fileStem(path));
}

function fileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function fileStem(path: string): string {
  return fileName(path).replace(/\.[^.]+$/, "");
}

function parentName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 1 ? parts.at(-2) ?? "" : "";
}

function normalizeQuery(value: string): string {
  return value.replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim();
}
