import type { ReactNode } from "react";

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
  { id: "dashboard", label: "Dashboard" },
  { id: "manual", label: "Manual Organizer" },
  { id: "monitors", label: "Automatic Monitors" },
  { id: "review", label: "Review Queue" },
  { id: "tasks", label: "Task Center" },
  { id: "actors", label: "Actor Library" },
  { id: "history", label: "History/Rollback" },
  { id: "settings", label: "Settings" },
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            X
          </span>
          <div>
            <h1>Xona</h1>
            <p>Local organizer</p>
          </div>
        </div>
        <nav aria-label="Primary">
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
          <p className="eyebrow">Xona</p>
          <h2>{activeItem?.label ?? "Dashboard"}</h2>
        </header>
        {children}
      </main>
    </div>
  );
}
