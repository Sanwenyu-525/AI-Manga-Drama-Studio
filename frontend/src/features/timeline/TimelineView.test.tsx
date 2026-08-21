// Phase 9 — TimelineView smoke tests: create-empty state + rendered timeline
// (toolbar, clip block, render submit). API is mocked via client.api spies.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { Timeline } from "../../api/types";
import { TimelineView } from "./TimelineView";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  const wrapper = ({ children }: { children?: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

function notFound(code = "ENTITY_NOT_FOUND") {
  return Promise.reject(
    new client.ApiError(404, { error: { code, message: "not found", details: {} } }),
  );
}

function makeTimeline(clipShotId: string | null = null): Timeline {
  return {
    id: "tl1",
    project_id: "p1",
    episode_id: "e1",
    duration: 9,
    width: null,
    height: null,
    fps: null,
    status: "DRAFT",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    tracks: [
      { id: "t1", timeline_id: "tl1", track_type: "VIDEO", name: null, order_index: 0, locked: 0, muted: 0, created_at: "2026-08-01T00:00:00Z" },
      { id: "t2", timeline_id: "tl1", track_type: "SUBTITLE", name: null, order_index: 3, locked: 0, muted: 0, created_at: "2026-08-01T00:00:00Z" },
    ],
    clips: [
      {
        id: "c1",
        timeline_id: "tl1",
        track_id: "t1",
        asset_id: "a1",
        shot_id: clipShotId,
        start_time: 0,
        end_time: 3,
        source_in: 0,
        source_out: null,
        order_index: 0,
        enabled: 1,
        text: null,
        asset: {
          id: "a1",
          type: "image",
          name: "EP01_SC01_SH01.png",
          status: "ready",
          version_group_id: "vg:shot:s1:SHOT_IMAGE",
          version_number: 2,
          thumbnail_url: null,
          mime_type: "image/png",
        },
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      },
    ],
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TimelineView", () => {
  it("shows the create state when the episode has no timeline and creates on click", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/timeline") return notFound();
      if (path === "/episodes/e1/final-video") return notFound();
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);
    const post = vi.fn().mockResolvedValue(makeTimeline());
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    const { wrapper } = makeWrapper();
    render(<TimelineView projectId="p1" episodeId="e1" />, { wrapper });

    expect(await screen.findByText("为该集创建时间线")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /创建时间线/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/episodes/e1/timeline"));
  });

  it("renders a created timeline with clip block and submits a render", async () => {
    const timeline = makeTimeline();
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/timeline") return Promise.resolve(timeline);
      if (path === "/episodes/e1/final-video") return notFound();
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);
    const post = vi.fn().mockResolvedValue({ generation_id: "g1", timeline_id: "tl1" });
    vi.spyOn(client.api, "post").mockImplementation(post as never);
    // clip select loads shot versions only when clip.shot_id exists — null here, so skip.

    const { wrapper } = makeWrapper();
    render(<TimelineView projectId="p1" episodeId="e1" />, { wrapper });

    expect(await screen.findByText("时间线")).toBeTruthy();
    expect(screen.getByText("一键排片")).toBeTruthy();
    // clip block on the VIDEO track shows its version badge
    expect(await screen.findByText("V2")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "渲染 / 导出" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/timelines/tl1/render"));
  });
});
