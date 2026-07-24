import { FormEvent, useState } from "react";

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
import { Tabs, type TabItem } from "../components/Tabs";
import { linesToList } from "./settings/settingsForm";

const safetyLabels = [
  ["file_conflict", "文件冲突拒绝"],
  ["unresolved_multipart", "未解决的分段文件"],
  ["incomplete_metadata", "元数据不完整"],
  ["unsafe_path", "不安全路径"],
  ["strict_assets_missing", "严格资源失败"],
] as const;

type SafetyKey = (typeof safetyLabels)[number][0];
type ManualTab = "scan" | "match" | "execute";

const manualTabs: readonly TabItem<ManualTab>[] = [
  { id: "scan", label: "扫描" },
  { id: "match", label: "匹配/复核" },
  { id: "execute", label: "预览/执行" },
];

export function ManualOrganizerPage() {
  const [activeTab, setActiveTab] = useState<ManualTab>("scan");
  const [directory, setDirectory] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [ignorePatterns, setIgnorePatterns] = useState("");
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
        setActiveTab("match");
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
      if (response.accepted) {
        setActiveTab("execute");
      }
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
    <div className="page-stack manual-workbench">
      <div className="workflow-progress" aria-label="手动整理流程">
        <WorkflowStep active={activeTab === "scan"} complete={jobs.length > 0} index={1} title="扫描" description="选择源目录并生成任务" />
        <WorkflowStep active={activeTab === "match"} complete={Boolean(selected)} index={2} title="匹配复核" description="搜索候选项并确认" />
        <WorkflowStep active={activeTab === "execute"} complete={Boolean(executeResult)} index={3} title="预览执行" description="生成计划后再落盘" />
      </div>

      <Tabs
        activeTab={activeTab}
        ariaLabel="手动整理视图"
        tabs={manualTabs}
        onChange={setActiveTab}
      />

      <div className="tab-panel" role="tabpanel">
        {activeTab === "scan" ? (
          <>
            <Section title="选择源目录">
              <form className="workbench-grid" onSubmit={scan}>
                <div className="path-field">
                  <FormField
                    description="从已配置的存储根里选择源目录，或手动粘贴容器内绝对路径。"
                    label="源目录"
                  >
                    <input
                      placeholder="/downloads/incoming"
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
                  description="包含子目录中的媒体文件。"
                  onChange={setRecursive}
                />
                <FormField
                  description="每行一个 glob，用于跳过样片、系统目录等无关文件。"
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
                  <p className="muted">扫描后会自动进入“匹配/复核”。</p>
                </div>
              </form>
            </Section>
            <JobSummary jobs={jobs} onPick={(job) => setJobId(String(job.job_id))} />
          </>
        ) : null}

        {activeTab === "match" ? (
          <>
            <JobSummary jobs={jobs} onPick={(job) => setJobId(String(job.job_id))} />
            <Section title="搜索候选项">
              <div className="grid four">
                <FormField label="任务 ID">
                  <input
                    placeholder="扫描后自动填入，例如 12"
                    value={jobId}
                    onChange={(event) => setJobId(event.target.value)}
                  />
                </FormField>
                <FormField label="粘贴文件名搜索">
                  <input
                    placeholder="SSIS-001.mp4"
                    value={filename}
                    onChange={(event) => setFilename(event.target.value)}
                  />
                </FormField>
                <FormField label="可编辑的标准化查询">
                  <input
                    placeholder="SSIS-001"
                    value={normalizedQuery}
                    onChange={(event) => setNormalizedQuery(event.target.value)}
                  />
                </FormField>
                <div className="button-column">
                  <button type="button" onClick={() => search()}>
                    搜索
                  </button>
                  <button
                    className="secondary"
                    disabled={!jobs.length}
                    type="button"
                    onClick={batchSearch}
                  >
                    批量搜索
                  </button>
                </div>
              </div>
            </Section>

            <Section title="候选项选择">
              <div className="grid three">
                <FormField label="详情 URL">
                  <input
                    placeholder="https://www.xchina.co/movie/xxxx"
                    value={detailUrl}
                    onChange={(event) => setDetailUrl(event.target.value)}
                  />
                </FormField>
                <CheckboxField
                  checked={strictAssets}
                  label="严格资源"
                  description="要求图片和元数据资源完整。"
                  onChange={setStrictAssets}
                />
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
              {candidates.length ? (
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
              ) : (
                <div className="empty-state">
                  <strong>还没有候选项</strong>
                  <span>先扫描任务，再用番号、文件名或详情 URL 搜索。</span>
                </div>
              )}
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
            </Section>
          </>
        ) : null}

        {activeTab === "execute" ? (
          <Section title="预览/执行">
            <div className="grid four">
              <div className="path-field">
                <FormField label="目标根目录">
                  <input
                    placeholder="/media/jav"
                    value={destinationRoot}
                    onChange={(event) => setDestinationRoot(event.target.value)}
                  />
                </FormField>
                <DirectoryPicker
                  initialPath={destinationRoot}
                  onSelect={setDestinationRoot}
                  title="选择目标根目录"
                />
              </div>
              <FormField label="整理模式">
                <select
                  value={mode}
                  onChange={(event) => setMode(event.target.value as OrganizationMode)}
                >
                  <option value="preview">预览</option>
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
                  placeholder={'{studio}\n{title}'}
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
        ) : null}
      </div>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? <p className="status error floating-status">{error}</p> : null}
    </div>
  );
}

function WorkflowStep({
  active,
  complete,
  description,
  index,
  title,
}: {
  active: boolean;
  complete: boolean;
  description: string;
  index: number;
  title: string;
}) {
  return (
    <div className={`progress-step${active ? " is-active" : ""}${complete ? " is-complete" : ""}`}>
      <b>{complete ? "✓" : index}</b>
      <span>
        <strong>{title}</strong>
        <small>{description}</small>
      </span>
    </div>
  );
}

function JobSummary({
  jobs,
  onPick,
}: {
  jobs: ManualJobSummary[];
  onPick: (job: ManualJobSummary) => void;
}) {
  if (!jobs.length) {
    return (
      <section className="empty-state">
        <strong>还没有扫描任务</strong>
        <span>选择源目录并扫描后，任务会显示在这里。</span>
      </section>
    );
  }

  return (
    <Section title="已扫描任务">
      <table>
        <caption>已扫描任务</caption>
        <thead>
          <tr>
            <th>任务</th>
            <th>状态</th>
            <th>标识</th>
            <th>文件</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.job_id}>
              <td>{job.job_id}</td>
              <td>{job.state}</td>
              <td>{job.media_identity}</td>
              <td>{job.media_items.map((item) => item.path).join(", ")}</td>
              <td>
                <button className="secondary" type="button" onClick={() => onPick(job)}>
                  选择任务
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}
