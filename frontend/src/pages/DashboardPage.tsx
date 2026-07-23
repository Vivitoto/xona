import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { ActorListResponse, JobListResponse, WatchRuleList } from "../api/types";

export function DashboardPage() {
  const [reviewCount, setReviewCount] = useState<number | null>(null);
  const [ruleCount, setRuleCount] = useState<number | null>(null);
  const [actorCount, setActorCount] = useState<number | null>(null);

  useEffect(() => {
    apiFetch<JobListResponse>("/api/jobs?state=review_required")
      .then((payload) => setReviewCount(payload.jobs.length))
      .catch(() => setReviewCount(null));
    apiFetch<WatchRuleList>("/api/watch-rules")
      .then((payload) => setRuleCount(payload.rules.length))
      .catch(() => setRuleCount(null));
    apiFetch<ActorListResponse>("/api/actors")
      .then((payload) => setActorCount(payload.actors.length))
      .catch(() => setActorCount(null));
  }, []);

  return (
    <div className="page-stack">
      <section className="section">
        <h2>Dashboard</h2>
        <div className="metric-grid">
          <Metric label="Review required" value={reviewCount} />
          <Metric label="Watch rules" value={ruleCount} />
          <Metric label="Actors cached" value={actorCount} />
        </div>
      </section>
      <section className="section">
        <h2>Current Workflow</h2>
        <div className="workflow-strip">
          <span>Scan</span>
          <span>Search</span>
          <span>Review</span>
          <span>Preview</span>
          <span>Execute</span>
          <span>Rollback</span>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value ?? "-"}</strong>
    </div>
  );
}
