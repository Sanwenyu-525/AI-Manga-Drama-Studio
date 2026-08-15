import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import { TitleBar } from "../components/TitleBar";
import { ProjectHome } from "../features/project/ProjectHome";
import { NewProjectPage } from "../features/project/NewProjectPage";
import { AssetsPage } from "../features/assets/AssetsPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { WorkflowsPage } from "../features/workflows/WorkflowsPage";
import { StudioPage, ScriptWorkspace, StoryboardWorkspace } from "../features/studio/StudioPage";
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
          // The studio workspace is URL-driven: /script and /storyboard/:sceneId are
          // the two real views. The bare index redirects to the default workspace.
          { index: true, element: <Navigate to="script" replace /> },
          { path: "script", element: <ScriptWorkspace /> },
          { path: "storyboard/:sceneId", element: <StoryboardWorkspace /> },
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
