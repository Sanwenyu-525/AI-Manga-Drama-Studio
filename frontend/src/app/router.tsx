import { createBrowserRouter } from "react-router-dom";
import { ProjectHome } from "../features/project/ProjectHome";
import { NewProjectPage } from "../features/project/NewProjectPage";
import { StudioPage } from "../features/studio/StudioPage";
import { VersionReviewPage } from "../features/storyboard/VersionReviewPage";

// Routes (frontend-ux §76): Project Home + per-project Studio workspace.
export const router = createBrowserRouter([
  { path: "/", element: <ProjectHome /> },
  { path: "/projects/new", element: <NewProjectPage /> },
  { path: "/projects/:projectId", element: <StudioPage /> },
  { path: "/projects/:projectId/shots/:shotId/versions", element: <VersionReviewPage /> },
]);
