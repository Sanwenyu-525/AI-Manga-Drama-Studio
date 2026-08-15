// P6-T002: resizable panel geometry — clamp + drag delta math.
import { describe, expect, it } from "vitest";
import { PANEL_BOUNDS, clampPanelSize, resizeWithDelta, applyVerticalResize } from "../lib/panels";

describe("panels — clampPanelSize", () => {
  it("clamps into [min, max] for each panel", () => {
    const e = PANEL_BOUNDS.explorer;
    expect(clampPanelSize(100, e, e.min)).toBe(e.min);
    expect(clampPanelSize(e.min, e, e.min)).toBe(e.min);
    expect(clampPanelSize(e.max, e, e.min)).toBe(e.max);
    expect(clampPanelSize(9999, e, e.min)).toBe(e.max);
    expect(clampPanelSize(e.min + 37, e, e.min)).toBe(e.min + 37);
  });
  it("falls back for NaN", () => {
    expect(clampPanelSize(NaN, PANEL_BOUNDS.right, 380)).toBe(380);
  });
  it("rounds fractional sizes", () => {
    expect(clampPanelSize(201.6, PANEL_BOUNDS.explorer, 300)).toBe(202);
  });
});

describe("panels — resizeWithDelta", () => {
  it("applies delta in the given direction and clamps", () => {
    const e = PANEL_BOUNDS.explorer;
    expect(resizeWithDelta(300, 40, e, e.min, 1)).toBe(340);
    expect(resizeWithDelta(300, -40, e, e.min, 1)).toBe(260);
    expect(resizeWithDelta(300, 50, e, e.min, -1)).toBe(250);
    expect(resizeWithDelta(398, 100, e, e.min, 1)).toBe(e.max); // clamped
  });
});

describe("panels — applyVerticalResize", () => {
  it("grows the left panel when dragging right and shrinks right within bounds", () => {
    const { explorerWidth, rightWidth } = applyVerticalResize("left", 300, 380, 40);
    expect(explorerWidth).toBe(340);
    expect(rightWidth).toBe(380); // within gutter budget, right unchanged
  });
  it("keeps left within max without touching the right panel", () => {
    const { explorerWidth, rightWidth } = applyVerticalResize("left", 390, 380, 60);
    expect(explorerWidth).toBe(PANEL_BOUNDS.explorer.max);
    expect(rightWidth).toBe(380); // the flexible middle column absorbs the change
  });
  it("grows the right panel when dragging left", () => {
    const { explorerWidth, rightWidth } = applyVerticalResize("right", 300, 380, -40);
    expect(rightWidth).toBe(420);
    expect(explorerWidth).toBe(300);
  });
  it("clamps right to its max", () => {
    const { rightWidth } = applyVerticalResize("right", 300, 470, -60);
    expect(rightWidth).toBe(PANEL_BOUNDS.right.max);
  });
});