import { describe, expect, it } from "vitest";
import {
  canonicalScriptPath,
  canonicalShotPath,
  canonicalStoryboardPath,
  canonicalTimelinePath,
  parseStudioRoute,
} from "../features/studio/studioRoute";

describe("studio route model", () => {
  it("parses canonical episode-aware workspaces", () => {
    expect(parseStudioRoute("/projects/p1/episodes/e1/script")).toMatchObject({
      projectId: "p1",
      episodeId: "e1",
      workspace: "script",
      legacy: false,
    });
    expect(parseStudioRoute("/projects/p1/episodes/e1/scenes/s1/storyboard")).toMatchObject({
      projectId: "p1",
      episodeId: "e1",
      sceneId: "s1",
      workspace: "storyboard",
      legacy: false,
    });
    expect(parseStudioRoute("/projects/p1/episodes/e1/scenes/s1/shots/sh1")).toMatchObject({
      projectId: "p1",
      episodeId: "e1",
      sceneId: "s1",
      shotId: "sh1",
      workspace: "shot",
      legacy: false,
    });
    expect(parseStudioRoute("/projects/p1/episodes/e1/timeline")).toMatchObject({
      projectId: "p1",
      episodeId: "e1",
      workspace: "timeline",
      legacy: false,
    });
  });

  it("marks old studio URLs as adapters", () => {
    expect(parseStudioRoute("/projects/p1/script")).toMatchObject({
      projectId: "p1",
      workspace: "script",
      legacy: true,
    });
    expect(parseStudioRoute("/projects/p1/storyboard/s1")).toMatchObject({
      projectId: "p1",
      sceneId: "s1",
      workspace: "storyboard",
      legacy: true,
    });
    expect(parseStudioRoute("/projects/p1/timeline")).toMatchObject({
      projectId: "p1",
      workspace: "timeline",
      legacy: true,
    });
  });

  it("builds deterministic canonical paths", () => {
    expect(canonicalScriptPath("p1", "e1")).toBe("/projects/p1/episodes/e1/script");
    expect(canonicalStoryboardPath("p1", "e1", "s1")).toBe("/projects/p1/episodes/e1/scenes/s1/storyboard");
    expect(canonicalShotPath("p1", "e1", "s1", "sh1")).toBe("/projects/p1/episodes/e1/scenes/s1/shots/sh1");
    expect(canonicalTimelinePath("p1", "e1")).toBe("/projects/p1/episodes/e1/timeline");
  });
});
