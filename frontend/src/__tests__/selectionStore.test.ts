// P1-E6-T01: key state store — selection derives cleanly (frontend-ux §44-46).
import { beforeEach, describe, expect, it } from "vitest";
import { useSelectionStore } from "../stores/selectionStore";

beforeEach(() => useSelectionStore.setState({ selection: { shotIds: [], assetIds: [], workspace: "storyboard" } }));

describe("selectionStore", () => {
  it("selecting a scene clears shot ids", () => {
    useSelectionStore.getState().selectShot("shot_1");
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["shot_1"]);
    useSelectionStore.getState().setScene("scene_9");
    expect(useSelectionStore.getState().selection.shotIds).toEqual([]);
    expect(useSelectionStore.getState().selection.sceneId).toBe("scene_9");
  });

  it("switching project resets episode/scene/shot scope", () => {
    useSelectionStore.getState().setProject("p1");
    useSelectionStore.getState().setEpisode("e1");
    useSelectionStore.getState().selectShot("s1");
    useSelectionStore.getState().setProject("p2");
    const sel = useSelectionStore.getState().selection;
    expect(sel.projectId).toBe("p2");
    expect(sel.episodeId).toBeUndefined();
    expect(sel.sceneId).toBeUndefined();
    expect(sel.shotIds).toEqual([]);
  });
});
