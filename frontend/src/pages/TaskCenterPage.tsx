import { useState } from "react";

import { apiFetch } from "../api/client";
import type {
  JobActionResponse,
  JobEventsResponse,
  JobSummaryRead,
} from "../api/types";
import { FormField, Section } from "../components/FormField";
import { JobTimeline } from "../components/JobTimeline";

export function TaskCenterPage() {
  const [jobId, setJobId] = useState("1");
  const [job, setJob] = useState<JobSummaryRead | null>(null);
  const [events, setEvents] = useState<JobEventsResponse["events"]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function loadJob() {
    setError("");
    setStatus("正在加载任务");
    try {
      const [jobResponse, eventResponse] = await Promise.all([
        apiFetch<JobSummaryRead>(`/api/jobs/${jobId}`),
        apiFetch<JobEventsResponse>(`/api/jobs/${jobId}/events`),
      ]);
      setJob(jobResponse);
      setEvents(eventResponse.events);
      setStatus("任务已加载");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载任务");
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
        setStatus(`任务状态 ${response.job.state}`);
      } else {
        setStatus(`任务状态 ${response.state}`);
      }
      await loadJob();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务操作失败");
    }
  }

  return (
    <div className="page-stack">
      <Section title="任务中心">
        <div className="grid four">
          <FormField label="任务 ID">
            <input value={jobId} onChange={(event) => setJobId(event.target.value)} />
          </FormField>
          <button type="button" onClick={loadJob}>
            加载任务
          </button>
          <button disabled={!job?.retryable} type="button" onClick={() => action("retry")}>
            重试
          </button>
          <button type="button" onClick={() => action("cancel")}>
            取消
          </button>
        </div>
        <button
          disabled={!job?.retry_emby_available}
          type="button"
          onClick={() => action("retry-emby")}
        >
          重试 Emby
        </button>
        {job ? (
          <dl className="metadata-list">
            <div>
              <dt>状态</dt>
              <dd>{job.state}</dd>
            </div>
            <div>
              <dt>媒体标识</dt>
              <dd>{job.media_identity}</dd>
            </div>
            <div>
              <dt>尝试次数</dt>
              <dd>
                {job.attempts}/{job.max_attempts}
              </dd>
            </div>
            <div>
              <dt>最近错误</dt>
              <dd>{job.last_error_code ?? "无"}</dd>
            </div>
          </dl>
        ) : null}
        <JobTimeline events={events} />
        {status ? <p className="status">{status}</p> : null}
        {error ? <p className="status error">{error}</p> : null}
      </Section>
    </div>
  );
}
