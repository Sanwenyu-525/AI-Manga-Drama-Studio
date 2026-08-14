import { createBrowserRouter } from "react-router-dom";
import { ProjectHome } from "../features/project/ProjectHome";
import { StudioPage } from "../features/studio/StudioPage";

// Routes (frontend-ux §76): Project Home + per-project Studio workspace.
export const router = createBrowserRouter([
  { path: "/", element: <ProjectHome /> },
  { path: "/projects/:projectId", element: <StudioPage /> },
]);
