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
      setError(exc instanceof Error ? exc.message : "Unable to load review queue");
    }
  }

  useEffect(() => {
    void loadQueue();
  }, []);

  return (
    <div className="page-stack">
      <Section title="Review Queue">
        <div className="row row-between">
          <p className="muted">
            Items stopped by confidence thresholds or safety gates.
          </p>
          <button type="button" onClick={loadQueue}>
            Refresh queue
          </button>
        </div>
        <table>
          <caption>Review required jobs</caption>
          <thead>
            <tr>
              <th>Job</th>
              <th>Identity</th>
              <th>Reasons</th>
              <th>Candidate</th>
              <th>Plan</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length ? (
              jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.media_identity}</td>
                  <td>{job.gate_reasons.join(", ") || "Review required"}</td>
                  <td>{candidateTitle(job.selected_candidate)}</td>
                  <td>{job.plan_id ?? "Not planned"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>No review jobs.</td>
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
    return "No candidate";
  }
  return typeof candidate.title === "string" ? candidate.title : "Candidate selected";
}
