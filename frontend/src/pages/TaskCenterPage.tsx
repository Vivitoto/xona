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
    setStatus("Loading job");
    try {
      const [jobResponse, eventResponse] = await Promise.all([
        apiFetch<JobSummaryRead>(`/api/jobs/${jobId}`),
        apiFetch<JobEventsResponse>(`/api/jobs/${jobId}/events`),
      ]);
      setJob(jobResponse);
      setEvents(eventResponse.events);
      setStatus("Job loaded");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load job");
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
        setStatus(`Job ${response.job.state}`);
      } else {
        setStatus(`Job ${response.state}`);
      }
      await loadJob();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Job action failed");
    }
  }

  return (
    <div className="page-stack">
      <Section title="Task Center">
        <div className="grid four">
          <FormField label="Job ID">
            <input value={jobId} onChange={(event) => setJobId(event.target.value)} />
          </FormField>
          <button type="button" onClick={loadJob}>
            Load job
          </button>
          <button disabled={!job?.retryable} type="button" onClick={() => action("retry")}>
            Retry
          </button>
          <button type="button" onClick={() => action("cancel")}>
            Cancel
          </button>
        </div>
        <button
          disabled={!job?.retry_emby_available}
          type="button"
          onClick={() => action("retry-emby")}
        >
          Retry Emby
        </button>
        {job ? (
          <dl className="metadata-list">
            <div>
              <dt>State</dt>
              <dd>{job.state}</dd>
            </div>
            <div>
              <dt>Media identity</dt>
              <dd>{job.media_identity}</dd>
            </div>
            <div>
              <dt>Attempts</dt>
              <dd>
                {job.attempts}/{job.max_attempts}
              </dd>
            </div>
            <div>
              <dt>Last error</dt>
              <dd>{job.last_error_code ?? "None"}</dd>
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
