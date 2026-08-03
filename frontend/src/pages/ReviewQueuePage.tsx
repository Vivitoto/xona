import { useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";

import { apiFetch } from "../api/client";
import type { JobListResponse, JobSummaryRead } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Section } from "../components/FormField";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { codeLabel, stateLabel } from "../components/ProgressLog";

export function ReviewQueuePage() {
  const [jobs, setJobs] = useState<JobSummaryRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadQueue() {
    setError("");
    setLoading(true);
    try {
      const response = await apiFetch<JobListResponse>(
        "/api/jobs?state=review_required",
      );
      setJobs(Array.isArray(response.jobs) ? response.jobs : []);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载复核队列");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadQueue();
  }, []);

  const plannedCount = jobs.filter((job) => job.plan_id).length;
  const safetyGateCount = jobs.filter((job) =>
    job.gate_reasons.some((reason) => reason.includes("unsafe")),
  ).length;

  return (
    <div className="page-stack">
      <div className="metric-grid">
        <div className="metric metric-warning">
          <span>待复核</span>
          <strong>{loading ? "-" : jobs.length}</strong>
          <small>等待确认</small>
        </div>
        <div className="metric metric-primary">
          <span>已准备整理</span>
          <strong>{loading ? "-" : plannedCount}</strong>
          <small>已有计划</small>
        </div>
        <div className="metric metric-warning">
          <span>安全门禁</span>
          <strong>{loading ? "-" : safetyGateCount}</strong>
          <small>unsafe 原因</small>
        </div>
      </div>

      <Section title="待复核项目">
        <div className="section-toolbar">
          <button className="button-compact" disabled={loading} type="button" onClick={loadQueue}>
            刷新队列
          </button>
        </div>

        {loading ? (
          <LoadingSkeleton rows={4} title="正在加载复核队列" variant="table" />
        ) : jobs.length ? (
          <div className="table-wrap">
            <table>
              <caption>需复核任务</caption>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>状态</th>
                  <th>标识</th>
                  <th>原因</th>
                  <th>候选项</th>
                  <th>计划</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <code>{job.id}</code>
                    </td>
                    <td>
                      <span className="status-pill status-pill-warning">
                        {stateLabel(job.state)}
                      </span>
                    </td>
                    <td>{job.media_identity}</td>
                    <td>
                      <ReasonList reasons={job.gate_reasons} />
                    </td>
                    <td>{candidateTitle(job.selected_candidate)}</td>
                    <td>
                      {job.plan_id ? <code>{job.plan_id}</code> : "未生成计划"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            actions={[{ label: "刷新队列", onClick: loadQueue }]}
            description="低置信度或安全门禁会显示在这里。"
            icon={ClipboardCheck}
            title="没有待复核任务"
          />
        )}

        {error ? (
          <p className="status error floating-status" role="alert">
            {error}
          </p>
        ) : null}
      </Section>
    </div>
  );
}

function ReasonList({ reasons }: { reasons: string[] }) {
  if (!reasons.length) {
    return <span className="status-pill status-pill-neutral">需要复核</span>;
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
