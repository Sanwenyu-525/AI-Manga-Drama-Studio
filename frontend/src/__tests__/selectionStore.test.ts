// P1-E6-T01: key state store — selection derives cleanly (frontend-ux §44-46).
import { beforeEach, describe, expect, it } from "vitest";
import { useSelectionStore } from "../stores/selectionStore";

beforeEach(() => useSelectionStore.setState({ selection: { shotIds: [], assetIds: [] } }));

describe("selectionStore", () => {
  it("selecting an asset and shot keeps only transient ids", () => {
    useSelectionStore.getState().selectShot("shot_1");
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["shot_1"]);
    useSelectionStore.getState().selectAsset("asset_1");
    expect(useSelectionStore.getState().selection.assetIds).toEqual(["asset_1"]);
  });

  it("clears shot and asset selection independently", () => {
    useSelectionStore.getState().selectShot("s1");
    useSelectionStore.getState().selectAsset("a1");
    useSelectionStore.getState().clearShots();
    expect(useSelectionStore.getState().selection.shotIds).toEqual([]);
    expect(useSelectionStore.getState().selection.assetIds).toEqual(["a1"]);
    useSelectionStore.getState().clearAssets();
    expect(useSelectionStore.getState().selection.assetIds).toEqual([]);
  });
});
