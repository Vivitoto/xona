import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { ActorListResponse, JobListResponse, WatchRuleList } from "../api/types";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

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
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Local media organizer</p>
          <h2>整理、复核、归档，一条流水线完成</h2>
          <p>
            Xona 会先扫描本地媒体，再匹配元数据、生成整理预览，最后按安全门禁执行复制、移动或链接。
          </p>
        </div>
        <div className="hero-card">
          <span>当前状态</span>
          <strong>{reviewCount ? "需要复核" : "待命中"}</strong>
          <small>{reviewCount ?? 0} 个任务等待处理</small>
        </div>
      </section>

      <section className="section dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Overview</p>
            <h2>运行概览</h2>
          </div>
          <span className="badge">实时读取</span>
        </div>
        <div className="metric-grid">
          <Metric label="待复核" value={reviewCount} hint="需要人工确认的匹配结果" tone="warning" />
          <Metric label="监控规则" value={ruleCount} hint="自动扫描目录规则" tone="primary" />
          <Metric label="已缓存演员" value={actorCount} hint="本地演员资料库条目" tone="success" />
        </div>
        {reviewCount === null && ruleCount === null && actorCount === null ? (
          <LoadingSkeleton
            description="读取待复核任务、监控规则和演员缓存统计。"
            rows={3}
            title="正在读取运行概览"
          />
        ) : null}
      </section>

      <section className="section dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Pipeline</p>
            <h2>当前流程</h2>
          </div>
        </div>
        <div className="workflow-strip">
          {[
            ["扫描", "收集待整理文件"],
            ["搜索", "匹配 XChina 元数据"],
            ["复核", "确认候选项和安全门禁"],
            ["预览", "生成操作计划"],
            ["执行", "落盘整理输出"],
            ["回滚", "必要时恢复"],
          ].map(([title, description], index) => (
            <span className="workflow-step" key={title}>
              <b>{index + 1}</b>
              <strong>{title}</strong>
              <small>{description}</small>
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
