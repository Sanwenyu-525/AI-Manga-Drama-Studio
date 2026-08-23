// P6-T013/T014/T015 — EntityVersionBlock: lists versions with badges, uploads a
// reference image → creates a version, and promotes a version to MASTER via the
// activate endpoint. Mocks the api client (no network).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LocationVersion } from "../api/types";
import { EntityVersionBlock } from "../features/libraries/EntityVersionBlock";
import type { CharacterVersion } from "../api/types";
import * as client from "../api/client";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const versions: CharacterVersion[] = [
  {
    id: "cv1",
    character_id: "char_1",
    version_number: 1,
    asset_id: "ast_1",
    name: null,
    description: null,
    status: "stale",
    checksum: "abc123",
    is_master: true,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "cv2",
    character_id: "char_1",
    version_number: 2,
    asset_id: "ast_2",
    name: null,
    description: null,
    status: "stale",
    checksum: "def456",
    is_master: false,
    created_at: "2026-08-02T00:00:00Z",
    updated_at: "2026-08-02T00:00:00Z",
  },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("EntityVersionBlock (character)", () => {
  it("lists versions with the MASTER badge and fetches the right query", async () => {
    const get = vi.fn().mockResolvedValue(versions);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<EntityVersionBlock kind="character" entityId="char_1" projectId="proj_1" />, { wrapper });
    expect(await screen.findByText(/V2/)).toBeTruthy();
    expect(screen.getAllByText(/★ MASTER/).length).toBeGreaterThan(0);
    expect(screen.getByText(/V1/)).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/characters/char_1/versions");
  });

  it("promotes a non-master version to MASTER via the activate endpoint", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(versions);
    const post = vi.fn().mockImplementation((path) => Promise.resolve(versions.find((v) => path.includes(v.id))));
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<EntityVersionBlock kind="character" entityId="char_1" projectId="proj_1" />, { wrapper });
    // two "设 MASTER" buttons (one per non-master version); the first belongs to v2
    const buttons = await screen.findAllByText("设 MASTER");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/characters/char_1/versions/cv2/activate"));
  });
});
describe("EntityVersionBlock (location)", () => {
  const locVersions: LocationVersion[] = [
    {
      id: "lv1",
      location_id: "loc_1",
      version_number: 2,
      asset_id: "ast_loc",
      name: null,
      description: null,
      status: "active",
      checksum: null,
      is_master: true,
      created_at: "",
      updated_at: "",
    },
  ];

  it("lists location versions and activates via the location endpoint", async () => {
    const get = vi
      .fn()
      .mockResolvedValue([
        ...locVersions,
        { ...locVersions[0], id: "lv2", version_number: 3, asset_id: "ast_loc2", is_master: false, status: "stale" },
      ]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue(locVersions[0]);
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<EntityVersionBlock kind="location" entityId="loc_1" projectId="proj_1" />, { wrapper });
    expect(await screen.findByText(/V3/)).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/locations/loc_1/versions");
    fireEvent.click(screen.getAllByText("设 MASTER")[0]);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/locations/loc_1/versions/lv2/activate"));
  });
});

describe("EntityVersionBlock upload → create version", () => {
  it("imports a reference image then registers it as a new version", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(versions);
    const upload = vi.fn().mockResolvedValue({ id: "ast_new", status: "ready" });
    const post = vi.fn().mockImplementation((path: string, _body?: unknown) => {
      if (path.includes("/versions"))
        return Promise.resolve({
          id: "cv3",
          version_number: 3,
          asset_id: "ast_new",
          is_master: false,
          status: "stale",
          checksum: null,
          created_at: "",
        });
      return Promise.resolve({});
    });
    vi.spyOn(client.api, "upload").mockImplementation(upload);
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    const { container } = render(<EntityVersionBlock kind="character" entityId="char_1" projectId="proj_1" />, {
      wrapper,
    });
    await screen.findByText(/V2/);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["x"], "ref.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    expect(upload.mock.calls[0][0]).toBe("/projects/proj_1/assets/import");
    await waitFor(() => expect(post).toHaveBeenCalledWith("/characters/char_1/versions", { asset_id: "ast_new" }));
  });
});
