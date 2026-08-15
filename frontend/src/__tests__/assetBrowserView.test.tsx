// P6-T016/T017 — Asset Browser: aggregates the project media grid from the tree,
// per-shot versions and character/location masters; supports type filtering and opens
// an inspector with a provenance entry. Mocks the api client by path.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssetBrowserView } from "../features/assets/AssetBrowserView";
import type { AssetVersionRead, Character, CharacterVersion, Location, ProjectTreeRead, Project, ProvenanceRead } from "../api/types";
import * as client from "../api/client";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const project: Project = { id: "proj_1", name: "P", description: null, status: "active", aspect_ratio: null, fps: null, cover_url: null, revision: 1, created_at: "", updated_at: "" };

const shotVersion: AssetVersionRead = {
  id: "ast_1", shot_id: "shot_1", asset_id: "ast_1", media_type: "image", version_number: 1,
  generation_id: null, is_active: true, status: "ready", notes: null, created_at: "2026-08-01T00:00:00Z",
};

const tree: ProjectTreeRead = {
  project,
  episodes: [{
    id: "ep_1", episode_number: 1, title: null, scene_count: 1,
    scenes: [{ id: "sc_1", scene_number: 1, name: null, shot_count: 1, shots: [{ id: "shot_1", shot_number: 1, shot_type: "medium", status: "ready", dirty_state: "clean", revision: 1, active_image_version: 1, active_video_version: null, active_prompt_version_id: null }] }],
  }],
};

const characters: Character[] = [{ id: "char_1", project_id: "proj_1", name: "沈亦", alias: null, gender: null, age_description: null, appearance: null, personality: null, visual_prompt: null, negative_prompt: null, default_costume_id: null, status: "active", revision: 1, shot_count: 1, master_version_id: "cv1", created_at: "", updated_at: "" }];
const charVersions: CharacterVersion[] = [{ id: "cv1", character_id: "char_1", version_number: 4, asset_id: "ast_char_master", name: null, description: null, status: "active", checksum: "1234", is_master: true, created_at: "", updated_at: "" }];
const locations: Location[] = [];

const provenance: ProvenanceRead = {
  asset: { id: "ast_char_master", project_id: "proj_1", type: "image", name: "沈亦 master", file_path: "CHAR_1.png", mime_type: "image/png", width: 512, height: 768, status: "ready", source_type: "imported", version_group_id: null, version_number: 4, generation_id: null, parent_asset_id: null, meta: null, created_at: "" },
  generation: null, inputs: [], retry_of: null, parent_asset_id: null, ancestors: [],
};

function mockApi() {
  vi.spyOn(client.api, "get").mockImplementation((path: string) => {
    if (path === "/projects/proj_1/tree") return Promise.resolve(tree);
    if (path === "/projects/proj_1/characters") return Promise.resolve(characters);
    if (path === "/projects/proj_1/locations") return Promise.resolve(locations);
    if (path === "/shots/shot_1/versions") return Promise.resolve([shotVersion]);
    if (path === "/characters/char_1/versions") return Promise.resolve(charVersions);
    if (path === "/assets/ast_char_master/provenance") return Promise.resolve(provenance);
    if (path === "/assets/ast_1/provenance") return Promise.resolve({ ...provenance, asset: { ...provenance.asset, id: "ast_1" } });
    return Promise.resolve([]);
  });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("AssetBrowserView", () => {
  it("renders a grid of storyboard + MASTER reference assets with filters", async () => {
    mockApi();
    const { wrapper } = makeWrapper();
    render(<AssetBrowserView projectId="proj_1" />, { wrapper });
    expect(await screen.findByText(/EP01 · SC01 · SH001/)).toBeTruthy();
    expect(screen.getByText(/角色 · 沈亦/)).toBeTruthy();
    // type filter tab exists and filters to character masters only
    fireEvent.click(screen.getByText("角色"));
    await waitFor(() => expect(screen.queryByText(/EP01 · SC01 · SH001/)).toBeNull());
    expect(screen.getByText(/角色 · 沈亦/)).toBeTruthy();
  });

  it("opens the inspector and shows the provenance entry button when selected", async () => {
    mockApi();
    const { wrapper } = makeWrapper();
    render(<AssetBrowserView projectId="proj_1" />, { wrapper });
    const card = await screen.findByTitle(/角色 · 沈亦/);
    fireEvent.click(card);
    expect(await screen.findByText(/沈亦 master/)).toBeTruthy();
    // provenance button present once detail loads
    const provenanceBtn = await screen.findByText("查看溯源");
    expect(provenanceBtn).toBeTruthy();
  });
});
