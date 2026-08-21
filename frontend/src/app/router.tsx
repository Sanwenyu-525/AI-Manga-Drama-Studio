import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import { TitleBar } from "../components/TitleBar";
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
import { VersionReviewPage } from "../features/storyboard/VersionReviewPage";
import { NotFoundPage } from "../components/NotFoundPage";

// Routes (frontend-ux §76): the layout route renders the desktop window frame
// (custom title bar + routed content) so the TitleBar can use router navigation.
function AppFrame() {
  return (
    <div className="app-frame">
      <TitleBar />
      <div className="app-frame-content">
        <Outlet />
      </div>
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
          // Canonical routes are episode-aware; tabs only mirror these URLs.
          { index: true, element: <Navigate to="script" replace /> },
          { path: "episodes/:episodeId/script", element: <ScriptWorkspace /> },
          { path: "episodes/:episodeId/scenes/:sceneId/storyboard", element: <StoryboardWorkspace /> },
          { path: "episodes/:episodeId/scenes/:sceneId/shots/:shotId", element: <ShotDetailWorkspace /> },
          { path: "episodes/:episodeId/timeline", element: <TimelineWorkspace /> },
          { path: "assets", element: <AssetWorkspace /> },
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
