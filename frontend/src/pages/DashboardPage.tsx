import {
  FilePenLine,
  ListChecks,
  Search,
  ScrollText,
} from "lucide-react";

import type { PageId } from "../components/AppLayout";

export function DashboardPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
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
            <p className="eyebrow">Workflow</p>
            <h2>流程示例</h2>
          </div>
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
