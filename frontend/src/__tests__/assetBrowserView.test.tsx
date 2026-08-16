// P6-T016/T017 — Asset Browser now lists from the server project-asset endpoint
// (GET /projects/{id}/assets → {total, items}, type filter param); the inspector reads
// GET /assets/{id}. Mocks the api client by path.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssetBrowserView } from "../features/assets/AssetBrowserView";
import type { AssetListRead, AssetRead } from "../api/types";
import * as client from "../api/client";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

function asset(over: Partial<AssetRead> & { id: string }): AssetRead {
  return {
    project_id: "proj_1",
    type: "image",
    name: null,
    file_path: null,
    thumbnail_path: null,
    mime_type: "image/png",
    width: 512,
    height: 768,
    duration: null,
    file_size: 2048,
    meta: null,
    version_group_id: null,
    version_number: 1,
    status: "ready",
    source_type: "generated",
    checksum: "abcd1234efgh5678",
    generation_id: null,
    parent_asset_id: null,
    created_at: "2026-08-01T00:00:00Z",
    ...over,
  };
}

const shotAsset = asset({ id: "ast_1", name: "EP01 · SC01 · SH001", source_type: "generated" });
const charMaster = asset({ id: "ast_char_master", name: "沈亦 master", source_type: "character_master", version_number: 4, status: "active" });
const video = asset({ id: "ast_video", type: "video", name: "clip vid", source_type: "generated" });

function list(): AssetListRead {
  return { total: 3, items: [shotAsset, charMaster, video] };
}

function mockApi() {
  vi.spyOn(client.api, "get").mockImplementation((path: string) => {
    if (path.startsWith("/projects/proj_1/assets")) {
      const t = /type=([a-z]+)/.exec(path);
      if (t?.[1]) {
        const filtered = list().items.filter((a) => a.type === t[1]);
        return Promise.resolve({ total: filtered.length, items: filtered });
      }
      return Promise.resolve(list());
    }
    const m = /^\/assets\/(.+)$/.exec(path);
    if (m) {
      const found = list().items.find((a) => a.id === m[1]) ?? shotAsset;
      return Promise.resolve(found);
    }
    return Promise.resolve([]);
  });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("AssetBrowserView", () => {
  it("renders server-listed assets with source labels and MASTER flags", async () => {
    mockApi();
    const { wrapper } = makeWrapper();
    render(<AssetBrowserView projectId="proj_1" />, { wrapper });
    expect(await screen.findByText(/EP01 · SC01 · SH001/)).toBeTruthy();
    expect(screen.getByText(/沈亦 master/)).toBeTruthy();
    // the character MASTER tile shows the MASTER flag
    expect(screen.getByTitle("沈亦 master · V4")).toBeTruthy();
  });

  it("server-side filters by type (video) and keeps the type-filter UI", async () => {
    mockApi();
    const { wrapper } = makeWrapper();
    render(<AssetBrowserView projectId="proj_1" />, { wrapper });
    fireEvent.click(screen.getByText("视频"));
    // after server filter, only the video asset remains
    await waitFor(() => expect(screen.queryByText(/EP01 · SC01 · SH001/)).toBeNull());
    expect(await screen.findByText(/clip vid/)).toBeTruthy();
  });

  it("opens the inspector and shows server detail fields after selection", async () => {
    mockApi();
    const { wrapper } = makeWrapper();
    render(<AssetBrowserView projectId="proj_1" />, { wrapper });
    const card = await screen.findByTitle("沈亦 master · V4");
    fireEvent.click(card);
    // detail from GET /assets/{id} → status/version/file-size/checksum (async)
    expect(await screen.findByText("生效")).toBeTruthy();
    expect(screen.getByText("2.0 KB")).toBeTruthy();
    expect(screen.getByText("abcd1234efgh5678")).toBeTruthy();
    // provenance drawer button present
    expect(await screen.findByText("查看溯源")).toBeTruthy();
  });
});
