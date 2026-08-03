import { useEffect, useState } from "react";
import {
  FilePenLine,
  ListChecks,
  Search,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

import { apiFetch } from "../api/client";
import type { ActorListResponse } from "../api/types";
import type { PageId } from "../components/AppLayout";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

const dashboardShortcuts: Array<{
  title: string;
  description: string;
  buttonLabel: string;
  page: PageId;
  icon: LucideIcon;
}> = [
  {
    title: "未处理文件",
    description: "扫描目录或处理单个视频，生成本地 NFO、封面和整理预览。",
    buttonLabel: "打开未处理文件",
    page: "localMetadata",
    icon: FilePenLine,
  },
  {
    title: "元数据复核",
    description: "按标题搜索 XChina，确认可用条目后再带回本地草稿。",
    buttonLabel: "打开元数据复核",
    page: "xchinaSearch",
    icon: Search,
  },
  {
    title: "任务与记录",
    description: "查看整理计划、执行状态和失败条目。",
    buttonLabel: "查看任务记录",
    page: "tasks",
    icon: ListChecks,
  },
  {
    title: "历史线索",
    description: "从最近日志排查本地生成、执行和缓存问题。",
    buttonLabel: "查看日志",
    page: "logs",
    icon: ScrollText,
  },
];

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
          <p className="eyebrow">Workflow</p>
          <h2>媒体工作台</h2>
          <p>从未处理文件开始，补齐元数据和封面，再查看整理记录与日志。</p>
        </div>
        <div className="hero-actions">
          <button className="primary" type="button" onClick={() => onNavigate("localMetadata")}>
            <FilePenLine className="button-icon" size={16} strokeWidth={2.2} />
            本地元数据生成
          </button>
          <button className="secondary" type="button" onClick={() => onNavigate("xchinaSearch")}>
            <Search className="button-icon" size={16} strokeWidth={2.2} />
            XChina 元数据搜索
          </button>
          <button className="secondary" type="button" onClick={() => onNavigate("tasks")}>
            <ListChecks className="button-icon" size={16} strokeWidth={2.2} />
            整理记录
          </button>
          <button className="secondary" type="button" onClick={() => onNavigate("logs")}>
            <ScrollText className="button-icon" size={16} strokeWidth={2.2} />
            日志
          </button>
        </div>
      </section>

      <section className="section dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Shortcuts</p>
            <h2>常用入口</h2>
          </div>
        </div>
        <div className="entry-grid dashboard-shortcuts">
          {dashboardShortcuts.map((shortcut) => (
            <ShortcutCard key={shortcut.title} shortcut={shortcut} onNavigate={onNavigate} />
          ))}
        </div>
        {actorCount === null ? (
          <LoadingSkeleton rows={2} title="正在读取演员库" />
        ) : null}
        <div className="metric-grid metric-grid-compact">
          <Metric
            label="演员库"
            value={actorCount}
            hint="本地演员条目"
            tone="warning"
          />
        </div>
        <div className="workflow-strip dashboard-workflow" aria-label="整理流程">
          {["扫描", "草稿", "封面/NFO", "预览", "记录"].map((step, index) => (
            <span className="workflow-step" key={step}>
              <b>{index + 1}</b>
              <strong>{step}</strong>
              <small>本地流程</small>
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}

function ShortcutCard({
  onNavigate,
  shortcut,
}: {
  onNavigate: (page: PageId) => void;
  shortcut: {
    title: string;
    description: string;
    buttonLabel: string;
    page: PageId;
    icon: LucideIcon;
  };
}) {
  const Icon = shortcut.icon;
  return (
    <article className="entry-card dashboard-shortcut-card">
      <Icon aria-hidden="true" size={20} strokeWidth={2.2} />
      <h3>{shortcut.title}</h3>
      <p>{shortcut.description}</p>
      <button className="secondary button-compact" type="button" onClick={() => onNavigate(shortcut.page)}>
        <Icon className="button-icon" size={15} strokeWidth={2.2} />
        {shortcut.buttonLabel}
      </button>
    </article>
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
