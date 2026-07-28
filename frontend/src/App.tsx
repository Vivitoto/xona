import { useState } from "react";

import { AppLayout, type PageId } from "./components/AppLayout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ImageSafetyModeProvider } from "./components/ImageSafetyMode";
import { ThemeModeProvider } from "./components/ThemeMode";
import { ActorLibraryPage } from "./pages/ActorLibraryPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryRollbackPage } from "./pages/HistoryRollbackPage";
import { LogsPage } from "./pages/LogsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TaskCenterPage } from "./pages/TaskCenterPage";
import { UnmatchedVideosPage } from "./pages/UnmatchedVideosPage";
import { XChinaSearchPage } from "./pages/XChinaSearchPage";
import "./styles.css";

export default function App() {
  const [activePage, setActivePage] = useState<PageId>("dashboard");
  const [imageSafetyModeEnabled, setImageSafetyModeEnabled] = useState(true);

  return (
    <ThemeModeProvider>
      <ImageSafetyModeProvider
        enabled={imageSafetyModeEnabled}
        onChange={setImageSafetyModeEnabled}
      >
        <AppLayout activePage={activePage} onNavigate={setActivePage}>
          <ErrorBoundary
            resetKey={activePage}
            onReturnHome={() => setActivePage("dashboard")}
          >
            {renderPage(activePage, setActivePage)}
          </ErrorBoundary>
        </AppLayout>
      </ImageSafetyModeProvider>
    </ThemeModeProvider>
  );
}

function renderPage(page: PageId, onNavigate: (page: PageId) => void) {
  switch (page) {
    case "localMetadata":
      return <UnmatchedVideosPage />;
    case "xchinaSearch":
      return <XChinaSearchPage />;
    case "tasks":
      return <TaskCenterPage />;
    case "actors":
      return <ActorLibraryPage />;
    case "history":
      return <HistoryRollbackPage />;
    case "logs":
      return <LogsPage />;
    case "settings":
      return <SettingsPage />;
    case "dashboard":
    default:
      return <DashboardPage onNavigate={onNavigate} />;
  }
}
