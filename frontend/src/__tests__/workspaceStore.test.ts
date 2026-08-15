// P6-T002: shell-level panel sizes live in the workspace store with clamping.
import { describe, expect, it } from "vitest";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { PANEL_BOUNDS } from "../lib/panels";

const defaults = () => {
  const s = useWorkspaceStore.getState();
  return {
    explorerWidth: s.explorerWidth,
    rightWidth: s.rightWidth,
    bottomDockHeight: s.bottomDockHeight,
    explorerCollapsed: s.explorerCollapsed,
    rightPanelCollapsed: s.rightPanelCollapsed,
    bottomDockExpanded: s.bottomDockExpanded,
  };
};

describe("workspaceStore — panel sizes", () => {
  it("starts from persisted defaults within panel bounds", () => {
    const d = defaults();
    expect(d.explorerWidth).toBeGreaterThanOrEqual(PANEL_BOUNDS.explorer.min);
    expect(d.explorerWidth).toBeLessThanOrEqual(PANEL_BOUNDS.explorer.max);
    expect(d.rightWidth).toBeGreaterThanOrEqual(PANEL_BOUNDS.right.min);
    expect(d.rightWidth).toBeLessThanOrEqual(PANEL_BOUNDS.right.max);
  });
  it("setPanelSize clamps into bounds", () => {
    useWorkspaceStore.getState().setPanelSize("explorer", 9999);
    expect(useWorkspaceStore.getState().explorerWidth).toBe(PANEL_BOUNDS.explorer.max);
    useWorkspaceStore.getState().setPanelSize("right", 1);
    expect(useWorkspaceStore.getState().rightWidth).toBe(PANEL_BOUNDS.right.min);
    useWorkspaceStore.getState().setPanelSize("bottom", 64);
    expect(useWorkspaceStore.getState().bottomDockHeight).toBe(PANEL_BOUNDS.bottom.min);
  });
  it("setPanelSize with expanded flag toggles collapsed", () => {
    useWorkspaceStore.getState().setPanelSize("explorer", 260, false);
    expect(useWorkspaceStore.getState().explorerCollapsed).toBe(false);
  });
});