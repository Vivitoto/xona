import type { ReactNode } from "react";

import { useImageSafetyMode } from "./ImageSafetyMode";

export type PageId =
  | "dashboard"
  | "manual"
  | "monitors"
  | "review"
  | "tasks"
  | "actors"
  | "history"
  | "settings";

export const navigationItems: { id: PageId; label: string }[] = [
  { id: "dashboard", label: "仪表盘" },
  { id: "manual", label: "手动整理" },
  { id: "monitors", label: "自动监控" },
  { id: "review", label: "复核队列" },
  { id: "tasks", label: "任务中心" },
  { id: "actors", label: "演员库" },
  { id: "history", label: "历史/回滚" },
  { id: "settings", label: "设置" },
];

export function AppLayout({
  activePage,
  onNavigate,
  children,
}: {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
}) {
  const activeItem = navigationItems.find((item) => item.id === activePage);
  const { imageSafetyModeEnabled, setImageSafetyModeEnabled } =
    useImageSafetyMode();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            X
          </span>
          <div>
            <h1>Xona</h1>
            <p>本地整理器</p>
          </div>
        </div>
        <nav aria-label="主导航">
          {navigationItems.map((item) => (
            <button
              key={item.id}
              aria-current={item.id === activePage ? "page" : undefined}
              className="nav-button"
              type="button"
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="content" tabIndex={-1}>
        <header className="page-header">
          <div className="page-title">
            <p className="eyebrow">Xona</p>
            <h2>{activeItem?.label ?? "仪表盘"}</h2>
          </div>
          <label
            className="image-safety-toggle"
            title="开启后候选图片和演员头像会默认模糊，悬停、聚焦或轻点图片可临时查看。"
          >
            <input
              aria-label="安全模式：模糊图片"
              checked={imageSafetyModeEnabled}
              type="checkbox"
              onChange={(event) => setImageSafetyModeEnabled(event.target.checked)}
            />
            <span>安全模式：模糊图片</span>
          </label>
        </header>
        {children}
      </main>
    </div>
  );
}
