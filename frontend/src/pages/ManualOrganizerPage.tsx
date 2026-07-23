import { FormEvent, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  BrowseResponse,
  ManualCandidateCard as ManualCandidate,
  ManualExecutePlanResponse,
  ManualJobSummary,
  ManualPreviewResponse,
  ManualScanResponse,
  ManualSearchResponse,
  OrganizationMode,
} from "../api/types";
import { CandidateCard } from "../components/CandidateCard";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { OperationPlanView } from "../components/OperationPlanView";
import { linesToList, listToLines } from "./settings/settingsForm";

const safetyLabels = [
  ["file_conflict", "文件冲突拒绝"],
  ["unresolved_multipart", "未解决的分段文件"],
  ["incomplete_metadata", "元数据不完整"],
  ["unsafe_path", "不安全路径"],
  ["strict_assets_missing", "严格资源失败"],
] as const;

type SafetyKey = (typeof safetyLabels)[number][0];

export function ManualOrganizerPage() {
  const [directory, setDirectory] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [ignorePatterns, setIgnorePatterns] = useState("");
  const [browseRootId, setBrowseRootId] = useState("1");
  const [browsePath, setBrowsePath] = useState("");
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [jobs, setJobs] = useState<ManualJobSummary[]>([]);
  const [jobId, setJobId] = useState("");
  const [filename, setFilename] = useState("");
  const [normalizedQuery, setNormalizedQuery] = useState("");
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

  async function browseSource() {
    setError("");
    const query = new URLSearchParams({
      root_id: browseRootId,
      path: browsePath,
    });
    try {
      setBrowse(await apiFetch<BrowseResponse>(`/api/storage-roots/browse?${query}`));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "浏览失败");
    }
  }

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
      }
      setStatus(`已扫描 ${response.scanned_count} 项`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "扫描失败");
    }
  }

  async function search(jobOverride?: number) {
    setStatus("正在搜索");
    setError("");
    try {
      const response = await apiFetch<ManualSearchResponse>("/api/manual/search", {
        method: "POST",
        body: {
          job_id: jobOverride ?? numericJobId(),
          filename: filename || null,
          normalized_query: normalizedQuery || null,
        },
      });
      setJobId(String(response.job_id));
      setNormalizedQuery(response.normalized_query);
      setCandidates(response.candidates);
      setStatus(`找到 ${response.candidates.length} 个候选项`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "搜索失败");
    }
  }

  async function batchSearch() {
    for (const job of jobs) {
      await search(job.job_id);
    }
  }

  async function selectCandidate(candidate: ManualCandidate | null = selected) {
    const activeJobId = numericJobId();
    if (!activeJobId) {
      setError("请先选择或输入任务再选择候选项。");
      return;
    }
    setError("");
    setStatus("正在选择候选项");
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
      setStatus(response.accepted ? "候选项已接受" : "需要复核");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "候选项选择失败");
    }
  }

  async function previewPlan() {
    const activeJobId = numericJobId();
    if (!activeJobId) {
      setError("预览前需要任务。");
      return;
    }
    setError("");
    setStatus("正在生成预览");
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
      setStatus("预览已就绪");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "预览失败");
    }
  }

  async function executePlan() {
    if (!preview) {
      return;
    }
    setError("");
    setStatus("正在执行");
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

  function numericJobId(): number | null {
    const parsed = Number.parseInt(jobId, 10);
    return Number.isFinite(parsed) ? parsed : null;
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
    <div className="page-stack">
      <Section title="源浏览/扫描">
        <form className="grid three" onSubmit={scan}>
          <FormField label="源目录">
            <input value={directory} onChange={(event) => setDirectory(event.target.value)} />
          </FormField>
          <CheckboxField checked={recursive} label="递归扫描" onChange={setRecursive} />
          <FormField label="忽略模式">
            <textarea
              value={ignorePatterns}
              onChange={(event) => setIgnorePatterns(event.target.value)}
            />
          </FormField>
          <button type="submit">扫描源目录</button>
        </form>
        <div className="grid three">
          <FormField label="浏览根 ID">
            <input value={browseRootId} onChange={(event) => setBrowseRootId(event.target.value)} />
          </FormField>
          <FormField label="浏览路径">
            <input value={browsePath} onChange={(event) => setBrowsePath(event.target.value)} />
          </FormField>
          <button type="button" onClick={browseSource}>
            浏览源目录
          </button>
        </div>
        {browse ? (
          <ul className="dense-list" aria-label="源浏览结果">
            {browse.entries.map((entry) => (
              <li key={entry.path}>
                <button
                  className="link-button"
                  type="button"
                  onClick={() => {
                    if (entry.is_dir) {
                      setDirectory(entry.path);
                      setBrowsePath(entry.path);
                    } else {
                      setFilename(entry.name);
                    }
                  }}
                >
                  {entry.name} {entry.is_dir ? "（目录）" : "（文件）"}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </Section>

      <Section title="搜索">
        <div className="grid four">
          <FormField label="任务 ID">
            <input value={jobId} onChange={(event) => setJobId(event.target.value)} />
          </FormField>
          <FormField label="粘贴文件名搜索">
            <input value={filename} onChange={(event) => setFilename(event.target.value)} />
          </FormField>
          <FormField label="可编辑的标准化查询">
            <input
              value={normalizedQuery}
              onChange={(event) => setNormalizedQuery(event.target.value)}
            />
          </FormField>
          <div className="button-column">
            <button type="button" onClick={() => search()}>
              搜索
            </button>
            <button disabled={!jobs.length} type="button" onClick={batchSearch}>
              批量搜索
            </button>
          </div>
        </div>
        {jobs.length ? (
          <table>
            <caption>已扫描任务</caption>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>标识</th>
                <th>文件</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id}>
                  <td>{job.job_id}</td>
                  <td>{job.state}</td>
                  <td>{job.media_identity}</td>
                  <td>{job.media_items.map((item) => item.path).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Section>

      <Section title="候选项选择">
        <div className="grid three">
          <FormField label="详情 URL">
            <input value={detailUrl} onChange={(event) => setDetailUrl(event.target.value)} />
          </FormField>
          <CheckboxField checked={strictAssets} label="严格资源" onChange={setStrictAssets} />
          <button type="button" onClick={() => selectCandidate()}>
            选择详情 URL
          </button>
        </div>
        <div className="safety-grid" aria-label="安全门禁">
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
        <div className="candidate-grid">
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
      </Section>

      <Section title="预览/执行">
        <div className="grid four">
          <FormField label="目标根目录">
            <input
              value={destinationRoot}
              onChange={(event) => setDestinationRoot(event.target.value)}
            />
          </FormField>
          <FormField label="整理模式">
            <select value={mode} onChange={(event) => setMode(event.target.value as OrganizationMode)}>
              <option value="preview">预览</option>
              <option value="copy">复制</option>
              <option value="move">移动</option>
              <option value="hardlink">硬链接</option>
              <option value="symlink">符号链接</option>
              <option value="in_place">原地处理</option>
            </select>
          </FormField>
          <FormField label="资源策略">
            <select value={assetPolicy} onChange={(event) => setAssetPolicy(event.target.value)}>
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
              value={folderTemplates}
              onChange={(event) => setFolderTemplates(event.target.value)}
            />
          </FormField>
          <FormField label="文件名模板">
            <input
              value={filenameTemplate}
              onChange={(event) => setFilenameTemplate(event.target.value)}
            />
          </FormField>
        </div>
        <div className="button-row">
          <button type="button" onClick={previewPlan}>
            预览操作计划
          </button>
          <button disabled={!preview} type="button" onClick={executePlan}>
            执行已批准预览
          </button>
        </div>
        <OperationPlanView preview={preview} refusalReasons={refusalReasons} />
        {executeResult ? (
          <p className="status">
            计划 {executeResult.plan_id} 状态为 {executeResult.state}
          </p>
        ) : null}
      </Section>

      {status ? <p className="status">{status}</p> : null}
      {error ? <p className="status error">{error}</p> : null}
    </div>
  );
}
