import { useEffect, useState } from "react";

import type { PageId } from "../components/AppLayout";
import { apiFetch } from "../api/client";
import type { ActorListResponse, JobListResponse, WatchRuleList } from "../api/types";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

export function DashboardPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
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
    <div className="page-stack dashboard-page">
      <section className="section dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Dashboard</p>
            <h2>首页</h2>
          </div>
        </div>
        <div className="button-row">
          <button type="button" onClick={() => onNavigate("manual")}>
            整理文件
          </button>
          <button className="secondary" type="button" onClick={() => onNavigate("settings")}>
            系统设置
          </button>
          <button className="secondary" type="button" onClick={() => onNavigate("monitors")}>
            监控规则
          </button>
        </div>
      </section>

      <section className="section dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Status</p>
            <h2>运行概览</h2>
          </div>
        </div>
        <div className="metric-grid metric-grid-compact">
          <Metric label="待复核" value={reviewCount} hint="待确认任务" tone="warning" />
          <Metric label="监控规则" value={ruleCount} hint="已配置规则" tone="primary" />
          <Metric label="演员缓存" value={actorCount} hint="本地条目" tone="success" />
        </div>
        {reviewCount === null && ruleCount === null && actorCount === null ? (
          <LoadingSkeleton rows={3} title="正在读取运行概览" />
        ) : null}
      </section>
    </div>
  );
}

function Metric({
  hint,
  label,
  tone,
  value,
}: {
  hint: string;
  label: string;
  tone: "primary" | "success" | "warning";
  value: number | null;
}) {
  return (
    <div className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value ?? "-"}</strong>
      <small>{hint}</small>
    </div>
  );
}
