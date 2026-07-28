import { useState } from "react";

import { apiFetch } from "../api/client";
import type {
  JobActionResponse,
  JobEventsResponse,
  JobSummaryRead,
} from "../api/types";
import { FormField, Section } from "../components/FormField";
import {
  ProgressLog,
  codeLabel,
  jobEventsToProgressLines,
  stateLabel,
} from "../components/ProgressLog";

export function TaskCenterPage() {
  const [jobId, setJobId] = useState("1");
  const [job, setJob] = useState<JobSummaryRead | null>(null);
  const [events, setEvents] = useState<JobEventsResponse["events"]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadJob() {
    setError("");
    setStatus("正在加载任务");
    setLoading(true);
    try {
      const [jobResponse, eventResponse] = await Promise.all([
        apiFetch<JobSummaryRead>(`/api/jobs/${jobId}`),
        apiFetch<JobEventsResponse>(`/api/jobs/${jobId}/events`),
      ]);
      setJob(jobResponse);
      setEvents(Array.isArray(eventResponse.events) ? eventResponse.events : []);
      setStatus("任务已加载");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载任务");
    } finally {
      setLoading(false);
    }
  }

  async function action(kind: "retry" | "cancel" | "retry-emby") {
    setError("");
    try {
      const path =
        kind === "retry-emby"
          ? `/api/jobs/${jobId}/retry-emby`
          : `/api/jobs/${jobId}/${kind}`;
      const response = await apiFetch<JobActionResponse | { job_id: number; state: string }>(
        path,
        { method: "POST" },
      );
      if ("job" in response) {
        setJob(response.job);
        setStatus(`任务状态：${stateLabel(response.job.state)}`);
      } else {
        setStatus(`任务状态：${stateLabel(response.state)}`);
      }
      await loadJob();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务操作失败");
    }
  }

  return (
    <div className="page-stack">
      <div className="metric-grid">
        <div className="metric metric-primary">
          <span>当前任务</span>
          <strong>{job ? `#${job.id}` : "-"}</strong>
          <small>{job?.media_identity ?? "输入任务 ID 后加载详情"}</small>
        </div>
        <div className="metric metric-warning">
          <span>任务状态</span>
          <strong>{loading ? "加载中" : job ? stateLabel(job.state) : "未加载"}</strong>
          <small>{job?.retryable ? "可重试" : "按任务状态控制操作"}</small>
        </div>
        <div className="metric metric-success">
          <span>进度记录</span>
          <strong>{events.length}</strong>
          <small>来自任务事件</small>
        </div>
      </div>

      <Section title="任务控制台">
        <div className="task-action-grid">
          <FormField label="任务 ID">
            <input
              placeholder="42"
              value={jobId}
              onChange={(event) => setJobId(event.target.value)}
            />
          </FormField>
          <button disabled={loading || !jobId} type="button" onClick={loadJob}>
            加载任务
          </button>
          <button disabled={!job?.retryable} type="button" onClick={() => action("retry")}>
            重试
          </button>
          <button disabled={!job} type="button" onClick={() => action("cancel")}>
            取消
          </button>
          <button
            disabled={!job?.retry_emby_available}
            type="button"
            onClick={() => action("retry-emby")}
          >
            重试 Emby
          </button>
        </div>
      </Section>

      <Section title="任务详情">
        {job ? (
          <dl className="metadata-list task-detail-list">
            <div>
              <dt>状态</dt>
              <dd>
                <span className={`status-pill ${stateTone(job.state)}`}>
                  {stateLabel(job.state)}
                </span>
              </dd>
            </div>
            <div>
              <dt>媒体标识</dt>
              <dd>{job.media_identity}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>{job.manual ? "本地元数据生成" : job.rule_id ? `规则任务 #${job.rule_id}` : "后台任务"}</dd>
            </div>
            <div>
              <dt>尝试次数</dt>
              <dd>
                {job.attempts}/{job.max_attempts}
              </dd>
            </div>
            <div>
              <dt>计划</dt>
              <dd>{job.plan_id ? <code>{job.plan_id}</code> : "未生成计划"}</dd>
            </div>
            <div>
              <dt>最近错误</dt>
              <dd>{job.last_error_code ? codeLabel(job.last_error_code) : "无"}</dd>
            </div>
            <div>
              <dt>候选项</dt>
              <dd>{candidateTitle(job.selected_candidate)}</dd>
            </div>
            <div>
              <dt>门禁原因</dt>
              <dd>
                <ReasonList reasons={job.gate_reasons} />
              </dd>
            </div>
          </dl>
        ) : (
          <div className="empty-state">
            <strong>还没有加载任务</strong>
            <span>输入任务 ID 后加载详情、进度记录和可用操作。</span>
          </div>
        )}
      </Section>

      <Section title="任务进度">
        <ProgressLog
          ariaLabel="任务进度日志"
          emptyLabel="加载任务后显示搜索、整理和通知进度。"
          lines={jobEventsToProgressLines(events, job?.state)}
        />
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? (
        <p className="status error floating-status" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ReasonList({ reasons }: { reasons: string[] }) {
  if (!reasons.length) {
    return <span className="status-pill status-pill-neutral">无</span>;
  }

  return (
    <div className="reason-list">
      {reasons.map((reason) => (
        <span className="status-pill status-pill-warning" key={reason}>
          {codeLabel(reason)}
        </span>
      ))}
    </div>
  );
}

function candidateTitle(candidate: Record<string, unknown> | null): string {
  if (!candidate) {
    return "无候选项";
  }
  return typeof candidate.title === "string" ? candidate.title : "已选择候选项";
}

function stateTone(state: string): string {
  if (["completed", "notifying_emby"].includes(state)) {
    return "status-pill-success";
  }
  if (["failed", "cancelled"].includes(state)) {
    return "status-pill-danger";
  }
  if (["review_required", "retrying"].includes(state)) {
    return "status-pill-warning";
  }
  return "status-pill-neutral";
}
