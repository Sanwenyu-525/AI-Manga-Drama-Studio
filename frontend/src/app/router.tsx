import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
// Frozen shell (DESIGN.md §4 / P0): header + context bar + body (activity rail +
// routed page) + system status bar. Present on every screen so the desktop app
// reads as one product instead of per-page layouts.
import { AppHeader } from "../components/shell/AppHeader";
import { ProjectContextBar } from "../components/shell/ProjectContextBar";
import { ActivityRail } from "../components/shell/ActivityRail";
import { SystemStatusBar } from "../components/shell/SystemStatusBar";
import { ProjectHome } from "../features/project/ProjectHome";
import { NewProjectPage } from "../features/project/NewProjectPage";
import { AssetsPage } from "../features/assets/AssetsPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { WorkflowsPage } from "../features/workflows/WorkflowsPage";
import {
  StudioPage,
  ScriptWorkspace,
  StoryboardWorkspace,
  ShotDetailWorkspace,
  AssetWorkspace,
  TimelineWorkspace,
  LegacyEpisodeRoute,
  LegacyStoryboardRoute,
} from "../features/studio/StudioPage";
import { PromptsHistoryPage } from "../features/prompts/PromptsHistoryPage";
import { ProductionLogPage } from "../features/log/ProductionLogPage";
import { WorkspaceOverviewPage } from "../features/workspace/WorkspaceOverviewPage";
import { SourceWorkspacePage } from "../features/source/SourceWorkspacePage";
import { VersionReviewPage } from "../features/storyboard/VersionReviewPage";
import { NotFoundPage } from "../components/NotFoundPage";
import {
  CharactersWorkspacePage,
  ContinuityWorkspacePage,
  DirectorWorkspacePage,
  KnowledgeWorkspacePage,
  LocationsWorkspacePage,
  ShotsIndexPage,
  StoryboardIndexPage,
} from "../features/navigation/RailWorkspacePages";

// Layout route: frozen shell wraps every routed page.
function AppFrame() {
  return (
    <div className="app-frame">
      <AppHeader />
      <ProjectContextBar />
      <div className="app-frame-body">
        <ActivityRail />
        <main className="app-frame-main">
          <Outlet />
        </main>
      </div>
      <SystemStatusBar />
    </div>
  );
}

export const router = createBrowserRouter([
  {
    element: <AppFrame />,
    children: [
      { path: "/", element: <ProjectHome /> },
      { path: "/projects/new", element: <NewProjectPage /> },
      { path: "/assets", element: <AssetsPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "/workflows", element: <WorkflowsPage /> },
      {
        path: "/projects/:projectId",
        element: <StudioPage />,
        children: [
          // 漫剧工作区默认首页 = P2 生产控制中心；剧本/分镜等由 Rail 二跳。
          { index: true, element: <Navigate to="workspace" replace /> },
          { path: "workspace", element: <WorkspaceOverviewPage /> },
          { path: "source", element: <SourceWorkspacePage /> },
          { path: "director", element: <DirectorWorkspacePage /> },
          { path: "characters", element: <CharactersWorkspacePage /> },
          { path: "locations", element: <LocationsWorkspacePage /> },
          { path: "storyboard", element: <StoryboardIndexPage /> },
          { path: "shots", element: <ShotsIndexPage /> },
          { path: "knowledge", element: <KnowledgeWorkspacePage /> },
          { path: "continuity", element: <ContinuityWorkspacePage /> },
          { path: "episodes/:episodeId/script", element: <ScriptWorkspace /> },
          { path: "episodes/:episodeId/scenes/:sceneId/storyboard", element: <StoryboardWorkspace /> },
          { path: "episodes/:episodeId/scenes/:sceneId/shots/:shotId", element: <ShotDetailWorkspace /> },
          { path: "episodes/:episodeId/timeline", element: <TimelineWorkspace /> },
          { path: "assets", element: <AssetWorkspace /> },
          { path: "prompts", element: <PromptsHistoryPage /> },
          { path: "production-log", element: <ProductionLogPage /> },
          // Legacy routes only resolve and redirect; they do not write Selection state.
          { path: "script", element: <LegacyEpisodeRoute workspace="script" /> },
          { path: "storyboard/:sceneId", element: <LegacyStoryboardRoute /> },
          { path: "timeline", element: <LegacyEpisodeRoute workspace="timeline" /> },
        ],
      },
      {
        path: "/projects/:projectId/shots/:shotId/versions",
        element: <VersionReviewPage />,
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
