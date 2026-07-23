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
        <h2>仪表盘</h2>
        <div className="metric-grid">
          <Metric label="待复核" value={reviewCount} />
          <Metric label="监控规则" value={ruleCount} />
          <Metric label="已缓存演员" value={actorCount} />
        </div>
      </section>
      <section className="section">
        <h2>当前流程</h2>
        <div className="workflow-strip">
          <span>扫描</span>
          <span>搜索</span>
          <span>复核</span>
          <span>预览</span>
          <span>执行</span>
          <span>回滚</span>
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
