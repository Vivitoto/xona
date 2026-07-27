import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  AppSettings,
  ManualCandidateCard as ManualCandidate,
  ManualExecutePlanResponse,
  ManualJobSummary,
  ManualScanResponse,
  ManualSearchResponse,
  ManualSelectCandidateResponse,
  OrganizationMode,
} from "../api/types";
import { CandidateCard } from "../components/CandidateCard";
import { DirectoryPicker } from "../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { useImageSafetyMode } from "../components/ImageSafetyMode";
import {
  ProgressLog,
  codeLabel,
  stateLabel,
  type ProgressLogLine,
  type ProgressLogTone,
} from "../components/ProgressLog";
import { TemplateGuide } from "../components/TemplateGuide";
import { proxiedImageUrl } from "../utils/imageProxy";
import { linesToList, listToLines, normalizeSettings } from "./settings/settingsForm";

const safetyLabels = [
  ["file_conflict", "文件冲突拒绝"],
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
  const [selectedMetadata, setSelectedMetadata] = useState<Record<string, unknown> | null>(null);
  const [detailUrl, setDetailUrl] = useState("");
  const [strictAssets, setStrictAssets] = useState(false);
  const [safety, setSafety] = useState<Record<SafetyKey, boolean>>({
    file_conflict: false,
    incomplete_metadata: false,
    unsafe_path: false,
    strict_assets_missing: false,
  });
  const [refusalReasons, setRefusalReasons] = useState<string[]>([]);
  const [selectionAccepted, setSelectionAccepted] = useState(false);
  const [destinationRoot, setDestinationRoot] = useState("");
  const [mode, setMode] = useState<OrganizationMode>("copy");
  const [folderTemplates, setFolderTemplates] = useState("{studio}\n{title}");
  const [filenameTemplate, setFilenameTemplate] = useState("{title}");
  const [assetPolicy, setAssetPolicy] = useState("lenient");
  const [includeSourceSnapshot, setIncludeSourceSnapshot] = useState(false);
  const [executeResult, setExecuteResult] =
    useState<ManualExecutePlanResponse | null>(null);
  const [organizing, setOrganizing] = useState(false);
  const [progressLines, setProgressLines] = useState<ProgressLogLine[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [searchState, setSearchState] = useState<
    "idle" | "searching" | "success" | "error"
  >("idle");
  const [searchFeedback, setSearchFeedback] = useState("");
  const [resultsFocused, setResultsFocused] = useState(false);
  const organizationConfigTouched = useRef(false);
  const progressCounter = useRef(0);

  const activeJob = useMemo(
    () => jobs.find((job) => String(job.job_id) === jobId) ?? jobs[0] ?? null,
    [jobId, jobs],
  );
  const activeMedia = activeJob?.media_items[0] ?? null;

  useEffect(() => {
    let active = true;
    apiFetch<AppSettings>("/api/settings")
      .then((payload) => {
        if (!active) {
          return;
        }
        applyOrganizationDefaults(normalizeSettings(payload));
      })
      .catch(() => {
        // Organizer defaults are a convenience; scanning/searching should still work.
      });
    return () => {
      active = false;
    };
  }, []);

  async function scan(event?: FormEvent) {
    event?.preventDefault();
    setStatus("正在扫描");
    setError("");
    resetProgressLog("扫描源目录", "active");
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
        resetForJob(response.jobs[0]);
      } else {
        setJobId("");
        clearSelectedCandidate();
      }
      setSearchState("idle");
      setSearchFeedback("");
      setResultsFocused(false);
      setStatus(`已扫描 ${response.scanned_count} 个视频文件`);
      pushProgressLog(`扫描完成：${response.scanned_count} 个视频文件`, "success");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "扫描失败";
      pushProgressLog(`扫描失败：${message}`, "danger");
      setError(message);
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
    setResultsFocused(false);
    setSearchFeedback(`正在搜索「${query}」…`);
    setStatus("");
    setError("");
    setCandidates([]);
    setSelected(null);
    setSelectedMetadata(null);
    setSelectionAccepted(false);
    setExecuteResult(null);
    pushProgressLog(`搜索 XChina：${query}`, "active");
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
      setResultsFocused(true);
      setSearchFeedback(
        response.candidates.length
          ? `搜索完成：找到 ${response.candidates.length} 个候选结果。`
          : `搜索完成：没有找到候选结果。`,
      );
      pushProgressLog(`搜索完成：${response.candidates.length} 个候选结果`, "success");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "搜索失败";
      setSearchState("error");
      setSearchFeedback(message);
      pushProgressLog(`搜索失败：${message}`, "danger");
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
    setSelectionAccepted(false);
    setStatus("正在刮削详情并校验");
    pushProgressLog("获取详情并校验", "active");
    try {
      const response = await apiFetch<ManualSelectCandidateResponse>(
        `/api/manual/jobs/${activeJobId}/select-candidate`,
        {
          method: "POST",
          body: {
            candidate_id: candidate?.candidate_id ?? null,
            source_url: detailUrl || candidate?.url || null,
            strict_assets: strictAssets,
            safety: safetyPayload(),
          },
        },
      );
      setSelected(response.selected_candidate ?? candidate);
      setSelectedMetadata(response.metadata ?? null);
      setRefusalReasons(response.reasons);
      setSelectionAccepted(response.accepted);
      setStatus(response.accepted ? "已选择候选结果，可以开始整理" : "需要人工复核");
      pushProgressLog(
        response.accepted ? "详情已获取：可以开始整理" : "需要人工复核",
        response.accepted ? "success" : "warning",
      );
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "候选项选择失败";
      setSelectionAccepted(false);
      pushProgressLog(`获取详情失败：${message}`, "danger");
      setError(message);
    }
  }

  async function startOrganization() {
    const activeJobId = activeJob?.job_id;
    if (!activeJobId) {
      setError("整理前需要选择一个视频文件。");
      return;
    }
    if (!selected) {
      setError("整理前需要选择一个候选结果。");
      return;
    }
    if (!selectionAccepted) {
      setError("整理前需要先通过候选校验。");
      return;
    }
    setError("");
    setExecuteResult(null);
    setOrganizing(true);
    setStatus("正在整理");
    pushProgressLog("规划整理", "active");
    try {
      const response = await apiFetch<ManualExecutePlanResponse>(
        `/api/manual/jobs/${activeJobId}/organize`,
        {
          method: "POST",
          body: {
            destination_root: destinationRoot,
            mode: organizationModeOrCopy(mode),
            folder_templates: linesToList(folderTemplates),
            filename_template: filenameTemplate,
            asset_policy: assetPolicy,
            include_source_snapshot: includeSourceSnapshot,
          },
        },
      );
      pushProgressLog("安全计划完成", "success");
      pushProgressLog("执行整理", "active");
      setExecuteResult(response);
      const label = organizationResultLabel(response.state);
      pushProgressLog(label, response.state === "failed" ? "danger" : "success");
      setStatus(label);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "整理失败";
      pushProgressLog(`整理失败：${message}`, "danger");
      setError(message);
    } finally {
      setOrganizing(false);
    }
  }

  function pickJob(job: ManualJobSummary) {
    resetForJob(job);
  }

  function resetForJob(job: ManualJobSummary) {
    setJobId(String(job.job_id));
    setQuerySource("filename");
    setSearchQuery(defaultQuery(job, "filename"));
    setCandidates([]);
    clearSelectedCandidate();
    setSearchState("idle");
    setSearchFeedback("");
    setResultsFocused(false);
  }

  function clearSelectedCandidate() {
    setSelected(null);
    setSelectedMetadata(null);
    setRefusalReasons([]);
    setSelectionAccepted(false);
    setExecuteResult(null);
  }

  function markOrganizationConfigTouched() {
    organizationConfigTouched.current = true;
  }

  function applyOrganizationDefaults(settings: AppSettings) {
    const defaults = settings.organization_defaults;
    const nextFolderTemplates = defaults.folder_templates.length
      ? defaults.folder_templates
      : settings.naming.folder_templates;
    const nextFilenameTemplate =
      defaults.filename_template || settings.naming.filename_template;

    setDestinationRoot((current) =>
      shouldPrefillText(current, organizationConfigTouched.current)
        ? defaults.destination_directory ?? ""
        : current,
    );
    setFolderTemplates((current) =>
      shouldPrefillText(current, organizationConfigTouched.current)
        ? listToLines(nextFolderTemplates)
        : current,
    );
    setFilenameTemplate((current) =>
      shouldPrefillText(current, organizationConfigTouched.current)
        ? nextFilenameTemplate
        : current,
    );
    setMode((current) =>
      organizationConfigTouched.current
        ? organizationModeOrCopy(current)
        : organizationModeOrCopy(defaults.organization_mode),
    );
    setAssetPolicy((current) =>
      organizationConfigTouched.current ? current : defaults.asset_policy,
    );
    setIncludeSourceSnapshot((current) =>
      organizationConfigTouched.current ? current : defaults.include_source_snapshot,
    );
  }

  function safetyPayload(): Record<string, boolean> {
    return {
      file_conflict: safety.file_conflict,
      unsafe_path: safety.unsafe_path,
      strict_assets_missing: safety.strict_assets_missing,
    };
  }

  function resetProgressLog(label: string, tone: ProgressLogTone = "neutral") {
    progressCounter.current += 1;
    const id = `progress-${progressCounter.current}`;
    setProgressLines([{ id, label, tone }]);
  }

  function pushProgressLog(label: string, tone: ProgressLogTone = "neutral") {
    progressCounter.current += 1;
    const id = `progress-${progressCounter.current}`;
    setProgressLines((current) => [
      ...current.slice(-10),
      { id, label, tone },
    ]);
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

              <div className="manual-search-controls">
                {resultsFocused && searchState === "success" ? (
                  <div className="results-refine-bar">
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => setResultsFocused(false)}
                    >
                      返回修改搜索
                    </button>
                    <span>当前关键词：{searchQuery}</span>
                  </div>
                ) : (
                  <>
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
                  </>
                )}
              </div>

              <div className="candidate-results-panel" aria-label="候选结果">
                <SearchFeedback
                  candidateCount={candidates.length}
                  feedback={searchFeedback}
                  state={searchState}
                />
                {selected ? (
                  <SelectedCandidateDetail candidate={selected} metadata={selectedMetadata} />
                ) : null}
                {candidates.length ? (
                  <div className="candidate-grid candidate-grid-compact">
                    {candidates.map((candidate) => (
                      <CandidateCard
                        key={candidate.candidate_id}
                        candidate={candidate}
                        selected={candidate.candidate_id === selected?.candidate_id}
                        onSelect={(nextCandidate) => {
                          setSelected(nextCandidate);
                          setSelectedMetadata(null);
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
                      <li key={reason}>{codeLabel(reason)}</li>
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

      <Section title="整理设置">
        <div className="grid four">
          <div className="path-field">
            <FormField label="目标目录">
              <input
                placeholder="/media/organized"
                value={destinationRoot}
                onChange={(event) => {
                  markOrganizationConfigTouched();
                  setDestinationRoot(event.target.value);
                }}
              />
            </FormField>
            <DirectoryPicker
              initialPath={destinationRoot}
              onSelect={(path) => {
                markOrganizationConfigTouched();
                setDestinationRoot(path);
              }}
              title="选择目标目录"
            />
          </div>
          <FormField label="整理模式">
            <select
              value={organizationModeOrCopy(mode)}
              onChange={(event) => {
                markOrganizationConfigTouched();
                setMode(event.target.value as OrganizationMode);
              }}
            >
              <option value="copy">复制</option>
              <option value="move">移动</option>
              <option value="hardlink">硬链接</option>
              <option value="symlink">符号链接</option>
              <option value="in_place">原地处理</option>
            </select>
          </FormField>
          <FormField label="资源缺失处理">
            <select
              value={assetPolicy}
              onChange={(event) => {
                markOrganizationConfigTouched();
                setAssetPolicy(event.target.value);
              }}
            >
              <option value="lenient">缺失继续整理</option>
              <option value="strict">缺失停止整理</option>
            </select>
          </FormField>
          <CheckboxField
            checked={includeSourceSnapshot}
            label="包含源快照"
            onChange={(checked) => {
              markOrganizationConfigTouched();
              setIncludeSourceSnapshot(checked);
            }}
          />
        </div>
        <div className="grid two">
          <FormField label="文件夹模板">
            <textarea
              placeholder={'{studio}\n{xchina_id} - {title}'}
              value={folderTemplates}
              onChange={(event) => {
                markOrganizationConfigTouched();
                setFolderTemplates(event.target.value);
              }}
            />
          </FormField>
          <FormField label="文件名模板">
            <input
              placeholder="{xchina_id} - {title}"
              value={filenameTemplate}
              onChange={(event) => {
                markOrganizationConfigTouched();
                setFilenameTemplate(event.target.value);
              }}
            />
          </FormField>
        </div>
        <TemplateGuide />
        <div className="button-row">
          <button
            disabled={!selected || !selectionAccepted || !destinationRoot || organizing}
            type="button"
            onClick={startOrganization}
          >
            {organizing ? "整理中…" : "开始整理"}
          </button>
        </div>
        <ProgressLog
          ariaLabel="整理进度日志"
          emptyLabel="选择候选结果并开始整理后显示进度。"
          lines={progressLines}
        />
        {executeResult ? (
          <p className="status">
            计划 {executeResult.plan_id}：{organizationResultLabel(executeResult.state)}
          </p>
        ) : null}
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? <p className="status error floating-status">{error}</p> : null}
    </div>
  );
}

function organizationModeOrCopy(mode: OrganizationMode): OrganizationMode {
  return mode === "preview" ? "copy" : mode;
}

function organizationResultLabel(state: string): string {
  if (state === "completed") {
    return "整理完成";
  }
  if (state === "previewed") {
    return "安全检查完成";
  }
  if (state === "failed") {
    return "整理失败";
  }
  return `整理状态：${state}`;
}

function SelectedCandidateDetail({
  candidate,
  metadata,
}: {
  candidate: ManualCandidate;
  metadata: Record<string, unknown> | null;
}) {
  const { imageSafetyModeEnabled } = useImageSafetyMode();
  const title = stringValue(metadata?.title) || candidate.title;
  const originalTitle = stringValue(metadata?.original_title);
  const source = stringValue(metadata?.source) || candidate.source;
  const sourceId = stringValue(metadata?.xchina_id) || candidate.source_candidate_id;
  const sourceUrl = stringValue(metadata?.source_url) || candidate.url;
  const releaseDate = stringValue(metadata?.release_date) || candidate.release_date;
  const studio = stringValue(metadata?.studio) || candidate.studio;
  const series = stringValue(metadata?.series) || candidate.series;
  const director = stringValue(metadata?.director);
  const runtimeMinutes = numberValue(metadata?.runtime_minutes);
  const plot = stringValue(metadata?.plot) || stringValue(metadata?.outline);
  const actors = metadataActors(metadata) || candidate.actors;
  const genres = stringList(metadata?.genres);
  const tags = stringList(metadata?.tags);
  const imageUrl = proxiedImageUrl(metadataPosterUrl(metadata) || candidate.image_url);
  const safetyLabel = imageSafetyModeEnabled
    ? `${title} 已选详情图片，安全模式已模糊，悬停、聚焦或轻点可临时查看`
    : `${title} 已选详情图片`;

  return (
    <article className="selected-candidate-detail" aria-label="已选候选详情">
      <div className="selected-candidate-poster">
        {imageUrl ? (
          <img
            alt={`${title} 已选详情图片`}
            aria-label={safetyLabel}
            className={`safety-image${imageSafetyModeEnabled ? " is-blurred" : ""}`}
            data-image-safety={imageSafetyModeEnabled ? "blurred" : "visible"}
            src={imageUrl}
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
            <div className="candidate-badges" aria-label="已选来源信息">
              <span>{source.toUpperCase()}</span>
              <span>ID {sourceId}</span>
              <span>匹配 {candidate.confidence_score}</span>
            </div>
            <h3>{title}</h3>
            {originalTitle ? <p className="muted">原标题：{originalTitle}</p> : null}
          </div>
          <a className="candidate-source-link" href={sourceUrl} target="_blank" rel="noreferrer">
            打开来源
          </a>
        </div>

        <dl className="metadata-list selected-detail-list">
          <div>
            <dt>演员</dt>
            <dd>{actors.length ? actors.join(", ") : "未知"}</dd>
          </div>
          <div>
            <dt>制作方</dt>
            <dd>{studio || "未知"}</dd>
          </div>
          <div>
            <dt>系列</dt>
            <dd>{series || "无"}</dd>
          </div>
          <div>
            <dt>日期</dt>
            <dd>{releaseDate || "未知"}</dd>
          </div>
          <div>
            <dt>导演</dt>
            <dd>{director || "未知"}</dd>
          </div>
          <div>
            <dt>时长</dt>
            <dd>{runtimeMinutes ? `${runtimeMinutes} 分钟` : "未知"}</dd>
          </div>
        </dl>

        {genres.length || tags.length ? (
          <div className="selected-candidate-chips" aria-label="类型和标签">
            {genres.map((genre) => (
              <span key={`genre:${genre}`}>{genre}</span>
            ))}
            {tags.map((tag) => (
              <span key={`tag:${tag}`}>{tag}</span>
            ))}
          </div>
        ) : null}

        {plot ? <p className="selected-candidate-plot">{plot}</p> : null}
      </div>
    </article>
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
      <div className="media-file-scroll">
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
              <span className="status-pill">{stateLabel(job.state)}</span>
            </button>
          );
        })}
      </div>
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

function shouldPrefillText(current: string, touched: boolean): boolean {
  return !touched || !current.trim();
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

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
    : [];
}

function metadataActors(metadata: Record<string, unknown> | null): string[] | null {
  const actors = metadata?.actors;
  if (!Array.isArray(actors)) {
    return null;
  }
  const names = actors
    .map((actor) => {
      if (typeof actor === "string") {
        return actor;
      }
      if (actor && typeof actor === "object" && "name" in actor) {
        return stringValue((actor as { name?: unknown }).name) ?? "";
      }
      return "";
    })
    .filter((name) => Boolean(name.trim()));
  return names.length ? names : null;
}

function metadataPosterUrl(metadata: Record<string, unknown> | null): string | null {
  const assets = metadata?.assets;
  if (!assets || typeof assets !== "object") {
    return null;
  }
  return stringValue((assets as { poster_url?: unknown; thumb_url?: unknown }).poster_url)
    ?? stringValue((assets as { poster_url?: unknown; thumb_url?: unknown }).thumb_url);
}
