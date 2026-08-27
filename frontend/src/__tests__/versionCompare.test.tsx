// P6-T012 — Version Compare (A/B): the review page shows two selected versions
// side by side, each with its own activate action. Mocks api by path inside a
// MemoryRouter + Routes so useParams resolves the projectId/shotId from the URL.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VersionReviewPage } from "../features/storyboard/VersionReviewPage";
import type { AssetVersionRead, Project, Shot } from "../api/types";
import * as client from "../api/client";

function renderReview() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/projects/proj_1/shots/shot_1/versions"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:projectId/shots/:shotId/versions" element={<VersionReviewPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const project: Project = {
  id: "proj_1",
  name: "P",
  description: null,
  status: "active",
  aspect_ratio: null,
  fps: null,
  cover_url: null,
  revision: 1,
  created_at: "",
  updated_at: "",
};
const shot: Shot = {
  id: "shot_1",
  scene_id: "sc_1",
  shot_number: 5,
  shot_order: 1,
  shot_type: "medium",
  camera_angle: null,
  camera_movement: null,
  lens: null,
  duration: null,
  action: null,
  emotion: null,
  dialogue: null,
  image_prompt: null,
  character_ids: [],
  status: "ready",
  dirty_state: "clean",
  revision: 1,
  created_at: "",
  updated_at: "",
};

const versions: AssetVersionRead[] = [
  {
    id: "ast_old",
    shot_id: "shot_1",
    asset_id: "ast_old",
    media_type: "image",
    version_number: 1,
    generation_id: "g1",
    is_active: true,
    status: "stale",
    notes: null,
    created_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "ast_new",
    shot_id: "shot_1",
    asset_id: "ast_new",
    media_type: "image",
    version_number: 2,
    generation_id: "g2",
    is_active: false,
    status: "ready",
    notes: null,
    created_at: "2026-08-02T00:00:00Z",
  },
];

function mockApi() {
  vi.spyOn(client.api, "get").mockImplementation((path: string) => {
    if (path === "/projects/proj_1") return Promise.resolve(project);
    if (path === "/shots/shot_1") return Promise.resolve(shot);
    if (path === "/shots/shot_1/versions") return Promise.resolve(versions);
    return Promise.resolve([]);
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("VersionReviewPage A/B compare", () => {
  it("opens the A/B board and shows two versions side by side", async () => {
    mockApi();
    renderReview();
    await screen.findByText("审片与定版"); // page loaded
    await screen.findByText("V1"); // versions loaded (sidebar + board)
    fireEvent.click(screen.getByRole("button", { name: (name: string) => name.includes("对比") }));
    // 工具栏按钮与 A/B 看板头部共用同一文案，故断言出现次数 ≥1
    expect((await screen.findAllByText("A/B 对比")).length).toBeGreaterThanOrEqual(1);
    // default A = active (V1), B = the other (V2): both side captions render
    expect(screen.getAllByText("V1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("V2").length).toBeGreaterThanOrEqual(1);
  });

  it("lets the user activate one side via its button", async () => {
    mockApi();
    const post = vi.fn().mockResolvedValue(versions[1]);
    vi.spyOn(client.api, "post").mockImplementation(post);
    renderReview();
    await screen.findByText("审片与定版");
    await screen.findByText("V1");
    fireEvent.click(screen.getByRole("button", { name: (name: string) => name.includes("对比") }));
    const activateButtons = await screen.findAllByText("激活此版本");
    expect(activateButtons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(activateButtons[0]);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/media-versions/ast_new/activate"));
  });
});
