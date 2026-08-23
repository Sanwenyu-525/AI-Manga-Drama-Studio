// P3 provenance panel test: renders asset info, generation block, inputs and
// the retry chain from GET /assets/{id}/provenance. Mocks the api client.
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProvenancePanel } from "../features/provenance/ProvenancePanel";
import * as client from "../api/client";
import type { ProvenanceRead } from "../api/types";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const provenance: ProvenanceRead = {
  asset: {
    id: "ast_asset_0001",
    project_id: "proj_1",
    type: "image",
    name: "Shot 003 V2",
    file_path: "EP01_SC03_SH005_IMG_V002.png",
    mime_type: "image/png",
    width: 1024,
    height: 1536,
    status: "ready",
    source_type: "generated",
    version_group_id: "vg:shot:s1:image",
    version_number: 2,
    generation_id: "gen_abc",
    parent_asset_id: null,
    meta: null,
    created_at: "2026-08-01T00:00:00Z",
  },
  generation: {
    id: "gen_abc",
    type: "image_generation",
    provider: "mock",
    model: "mock-image",
    workflow_id: "default_image_api",
    prompt_version_id: "pv_001",
    status: "completed",
    created_at: "2026-08-01T00:00:00Z",
    completed_at: "2026-08-01T00:01:00Z",
    parameters: '{"width": 1024, "seed": 42}',
  },
  inputs: [
    {
      id: "in_1",
      generation_id: "gen_abc",
      input_type: "reference",
      reference_type: "character",
      reference_id: "char_01",
      role: "actor",
      order_index: 0,
      metadata_json: null,
    },
    {
      id: "in_2",
      generation_id: "gen_abc",
      input_type: "prompt",
      reference_type: null,
      reference_id: null,
      role: "image_prompt",
      order_index: 1,
      metadata_json: '{"text":"a cat"}',
    },
  ],
  retry_of: "gen_prev",
  parent_asset_id: null,
  ancestors: ["gen_0", "gen_prev"],
};

const noProvenance: ProvenanceRead = {
  asset: {
    id: "ast_x",
    project_id: "p",
    type: "image",
    name: null,
    file_path: null,
    mime_type: null,
    width: null,
    height: null,
    status: "ready",
    source_type: "imported",
    version_group_id: null,
    version_number: null,
    generation_id: null,
    parent_asset_id: null,
    meta: null,
    created_at: null,
  },
  generation: null,
  inputs: [],
  retry_of: null,
  parent_asset_id: null,
  ancestors: [],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ProvenancePanel", () => {
  it("renders asset info, the producing generation and its inputs", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(provenance);
    const { wrapper } = makeWrapper();
    render(<ProvenancePanel assetId="ast_asset_0001" open onClose={() => {}} />, { wrapper });
    expect(await screen.findByText("生成记录")).toBeTruthy();
    expect(screen.getAllByText("mock").length).toBeGreaterThan(0);
    expect(screen.getByText("输入 (2)")).toBeTruthy();
    expect(screen.getByText("actor")).toBeTruthy();
    expect(client.api.get).toHaveBeenCalledWith("/assets/ast_asset_0001/provenance");
  });

  it("renders the retry chain from oldest ancestor to this generation", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(provenance);
    const { wrapper } = makeWrapper();
    render(<ProvenancePanel assetId="ast_asset_0001" open onClose={() => {}} />, { wrapper });
    await screen.findByText("来源链路");
    // the three chain nodes: two ancestors plus retry_of + this generation
    const nodes = screen.getAllByText(/gen_/);
    expect(nodes.length).toBeGreaterThanOrEqual(2);
  });

  it("shows an empty state when there is no provenance", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(noProvenance);
    const { wrapper } = makeWrapper();
    render(<ProvenancePanel assetId="ast_x" open onClose={() => {}} />, { wrapper });
    expect(await screen.findByText("这个资产没有溯源记录。")).toBeTruthy();
  });

  it("renders nothing when closed", () => {
    const { wrapper } = makeWrapper();
    render(<ProvenancePanel assetId="ast_x" open={false} onClose={() => {}} />, { wrapper });
    expect(screen.queryByText(/溯源/)).toBeNull();
  });
});
