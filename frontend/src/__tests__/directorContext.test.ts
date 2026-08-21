import { describe, expect, it } from "vitest";
import { buildDirectorContext } from "../features/director/useDirectorContext";
import type { StudioRoute } from "../features/studio/studioRoute";

const selection = { shotIds: ["shot-selected"], assetIds: ["asset-selected"] };

function route(partial: Partial<StudioRoute>): StudioRoute {
  return { projectId: "p1", workspace: "script", legacy: false, ...partial };
}

describe("Director context", () => {
  it("derives script context from the URL and clears transient selections", () => {
    expect(buildDirectorContext(route({ episodeId: "e1", workspace: "script" }), selection)).toEqual({
      workspace: "script",
      project_id: "p1",
      episode_id: "e1",
      scene_id: undefined,
      shot_ids: [],
      asset_ids: [],
    });
  });

  it("uses the shot detail URL as the authoritative shot selection", () => {
    expect(buildDirectorContext(route({ episodeId: "e1", sceneId: "s1", shotId: "sh1", workspace: "shot" }), selection)).toMatchObject({
      workspace: "storyboard",
      episode_id: "e1",
      scene_id: "s1",
      shot_ids: ["sh1"],
      asset_ids: [],
    });
  });

  it("keeps storyboard context on the URL scene while using temporary shot selection", () => {
    expect(buildDirectorContext(route({ episodeId: "e1", sceneId: "s1", workspace: "storyboard" }), selection)).toEqual({
      workspace: "storyboard",
      project_id: "p1",
      episode_id: "e1",
      scene_id: "s1",
      shot_ids: ["shot-selected"],
      asset_ids: [],
    });
  });

  it("keeps timeline context episode-aware without leaking shot or asset selection", () => {
    expect(buildDirectorContext(route({ episodeId: "e1", workspace: "timeline" }), selection)).toEqual({
      workspace: "timeline",
      project_id: "p1",
      episode_id: "e1",
      scene_id: undefined,
      shot_ids: [],
      asset_ids: [],
    });
  });

  it("only sends asset selection from the project asset workspace", () => {
    expect(buildDirectorContext(route({ workspace: "assets" }), selection)).toEqual({
      workspace: "assets",
      project_id: "p1",
      episode_id: undefined,
      scene_id: undefined,
      shot_ids: [],
      asset_ids: ["asset-selected"],
    });
  });
});
