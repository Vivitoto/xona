import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { ActorListResponse } from "../api/types";
import type { PageId } from "../components/AppLayout";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

export function DashboardPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [actorCount, setActorCount] = useState<number | null>(null);

  useEffect(() => {
    apiFetch<ActorListResponse>("/api/actors")
      .then((payload) => setActorCount(payload.actors.length))
      .catch(() => setActorCount(null));
  }, []);

  return (
    <div className="page-stack dashboard-page">
      <section className="hero-panel hero-panel-compact dashboard-hero">
        <div className="hero-copy">
          <p className="eyebrow">Dashboard</p>
          <h2>首页</h2>
          <p>本地媒体元数据工作台，聚焦本地生成与 XChina 元数据搜索。</p>
        </div>
        <div className="hero-actions">
          <button type="button" onClick={() => onNavigate("localMetadata")}>
            本地元数据生成
          </button>
          <button type="button" onClick={() => onNavigate("xchinaSearch")}>
            XChina 元数据搜索
          </button>
          <button className="secondary" type="button" onClick={() => onNavigate("tasks")}>
            整理记录
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
          <Metric label="本地生成" value="单个/批量" hint="NFO、封面与整理预览" tone="primary" />
          <Metric label="XChina 搜索" value="独立入口" hint="不依赖本地任务" tone="success" />
          <Metric label="演员库" value={actorCount} hint="本地条目" tone="warning" />
        </div>
        {actorCount === null ? (
          <LoadingSkeleton rows={3} title="正在读取运行概览" />
        ) : null}
        <div className="workflow-strip dashboard-workflow" aria-label="整理流程">
          {["本地文件", "元数据草稿", "封面/NFO", "整理预览", "整理记录"].map((step, index) => (
            <span className="workflow-step" key={step}>
              <b>{index + 1}</b>
              <strong>{step}</strong>
              <small>本地优先</small>
            </span>
          ))}
        </div>
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
  value: number | string | null;
}) {
  return (
    <div className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value ?? "-"}</strong>
      <small>{hint}</small>
    </div>
  );
}
