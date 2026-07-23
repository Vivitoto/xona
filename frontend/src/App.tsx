import { useState } from "react";

import { AppLayout, type PageId } from "./components/AppLayout";
import { ImageSafetyModeProvider } from "./components/ImageSafetyMode";
import { ActorLibraryPage } from "./pages/ActorLibraryPage";
import { AutomaticMonitorsPage } from "./pages/AutomaticMonitorsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryRollbackPage } from "./pages/HistoryRollbackPage";
import { ManualOrganizerPage } from "./pages/ManualOrganizerPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { SettingsPage } from "./pages/SettingsPage";
import { TaskCenterPage } from "./pages/TaskCenterPage";
import "./styles.css";

export default function App() {
  const [activePage, setActivePage] = useState<PageId>("dashboard");
  const [imageSafetyModeEnabled, setImageSafetyModeEnabled] = useState(true);

  return (
    <ImageSafetyModeProvider
      enabled={imageSafetyModeEnabled}
      onChange={setImageSafetyModeEnabled}
    >
      <AppLayout activePage={activePage} onNavigate={setActivePage}>
        {renderPage(activePage)}
      </AppLayout>
    </ImageSafetyModeProvider>
  );
}

function renderPage(page: PageId) {
  switch (page) {
    case "manual":
      return <ManualOrganizerPage />;
    case "monitors":
      return <AutomaticMonitorsPage />;
    case "review":
      return <ReviewQueuePage />;
    case "tasks":
      return <TaskCenterPage />;
    case "actors":
      return <ActorLibraryPage />;
    case "history":
      return <HistoryRollbackPage />;
    case "settings":
      return <SettingsPage />;
    case "dashboard":
    default:
      return <DashboardPage />;
  }
}
