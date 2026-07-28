import type { ReactNode } from "react";

import { APP_VERSION_LABEL } from "../appVersion";
import { useImageSafetyMode } from "./ImageSafetyMode";
import { useThemeMode } from "./ThemeMode";

export type PageId =
  | "dashboard"
  | "localMetadata"
  | "xchinaSearch"
  | "tasks"
  | "actors"
  | "history"
  | "logs"
  | "settings";

export const navigationItems: { id: PageId; label: string; icon: string }[] = [
  { id: "dashboard", label: "仪表盘", icon: "⌘" },
  { id: "localMetadata", label: "本地元数据生成", icon: "↳" },
  { id: "xchinaSearch", label: "XChina 元数据搜索", icon: "⌕" },
  { id: "tasks", label: "任务记录", icon: "☰" },
  { id: "actors", label: "演员库", icon: "◎" },
  { id: "history", label: "历史/回滚", icon: "↺" },
  { id: "logs", label: "日志", icon: "≋" },
  { id: "settings", label: "设置", icon: "⚙" },
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
  const { themeMode, toggleThemeMode } = useThemeMode();
  const themeToggleLabel = themeMode === "dark" ? "浅色模式" : "深色模式";

  return (
    <div className="app-shell" data-testid="app-theme-root" data-theme={themeMode}>
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
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.label}</span>
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
          <div className="page-header-actions">
            <span className="version-badge" aria-label={`Xona 版本 ${APP_VERSION_LABEL}`}>
              {APP_VERSION_LABEL}
            </span>
            <button
              className="theme-toggle"
              type="button"
              aria-label={themeToggleLabel}
              title={`切换到${themeToggleLabel}`}
              onClick={toggleThemeMode}
            >
              <span aria-hidden="true">{themeMode === "dark" ? "☼" : "☾"}</span>
              <span>{themeToggleLabel}</span>
            </button>
            <label
              className="image-safety-toggle"
              title="开启后候选图片和演员头像会默认模糊，悬停、聚焦或轻点图片可临时查看。"
            >
              <input
                aria-label="安全模式：模糊图片"
                checked={imageSafetyModeEnabled}
                type="checkbox"
                onChange={(event) =>
                  setImageSafetyModeEnabled(event.target.checked)
                }
              />
              <span>安全模式：模糊图片</span>
            </label>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
