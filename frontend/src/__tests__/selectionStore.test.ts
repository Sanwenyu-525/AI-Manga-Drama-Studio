// selectionStore multi-select semantics (autonomous-iteration-02).
import { beforeEach, describe, expect, it } from "vitest";
import { useSelectionStore } from "../stores/selectionStore";

describe("selectionStore multi-select", () => {
  beforeEach(() => {
    useSelectionStore.getState().clearShots();
  });

  it("selectShot keeps single-select replace semantics", () => {
    const store = useSelectionStore.getState();
    store.selectShot("a");
    store.selectShot("b");
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["b"]);
  });

  it("toggleShot adds and removes without clearing the rest", () => {
    const store = useSelectionStore.getState();
    store.toggleShot("a");
    store.toggleShot("b");
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["a", "b"]);
    store.toggleShot("a");
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["b"]);
  });

  it("setShotIds bulk-sets (shift range selection)", () => {
    useSelectionStore.getState().setShotIds(["s1", "s2", "s3"]);
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["s1", "s2", "s3"]);
  });

  it("clearShots empties the multi-selection", () => {
    useSelectionStore.getState().setShotIds(["s1", "s2"]);
    useSelectionStore.getState().clearShots();
    expect(useSelectionStore.getState().selection.shotIds).toEqual([]);
  });
});
