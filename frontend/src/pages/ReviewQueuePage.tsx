import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { JobListResponse, JobSummaryRead } from "../api/types";
import { Section } from "../components/FormField";

export function ReviewQueuePage() {
  const [jobs, setJobs] = useState<JobSummaryRead[]>([]);
  const [error, setError] = useState("");

  async function loadQueue() {
    setError("");
    try {
      const response = await apiFetch<JobListResponse>(
        "/api/jobs?state=review_required",
      );
      setJobs(response.jobs);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载复核队列");
    }
  }

  useEffect(() => {
    void loadQueue();
  }, []);

  return (
    <div className="page-stack">
      <Section title="复核队列">
        <div className="row row-between">
          <p className="muted">因置信度阈值或安全门禁而暂停的项目。</p>
          <button type="button" onClick={loadQueue}>
            刷新队列
          </button>
        </div>
        <table>
          <caption>需复核任务</caption>
          <thead>
            <tr>
              <th>任务</th>
              <th>标识</th>
              <th>原因</th>
              <th>候选项</th>
              <th>计划</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length ? (
              jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.media_identity}</td>
                  <td>{job.gate_reasons.join(", ") || "需要复核"}</td>
                  <td>{candidateTitle(job.selected_candidate)}</td>
                  <td>{job.plan_id ?? "未生成计划"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>没有待复核任务。</td>
              </tr>
            )}
          </tbody>
        </table>
        {error ? <p className="status error">{error}</p> : null}
      </Section>
    </div>
  );
}

function candidateTitle(candidate: Record<string, unknown> | null): string {
  if (!candidate) {
    return "无候选项";
  }
  return typeof candidate.title === "string" ? candidate.title : "已选择候选项";
}
