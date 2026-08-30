// P6-T002: resizable panel geometry — clamp + drag delta math.
import { describe, expect, it } from "vitest";
import { PANEL_BOUNDS, clampPanelSize, resizeWithDelta } from "../lib/panels";

describe("panels — clampPanelSize", () => {
  it("clamps into [min, max] for each panel", () => {
    const r = PANEL_BOUNDS.right;
    expect(clampPanelSize(100, r, r.min)).toBe(r.min);
    expect(clampPanelSize(r.min, r, r.min)).toBe(r.min);
    expect(clampPanelSize(r.max, r, r.min)).toBe(r.max);
    expect(clampPanelSize(9999, r, r.min)).toBe(r.max);
    expect(clampPanelSize(r.min + 37, r, r.min)).toBe(r.min + 37);
  });
  it("falls back for NaN", () => {
    expect(clampPanelSize(NaN, PANEL_BOUNDS.right, 380)).toBe(380);
  });
  it("rounds fractional sizes", () => {
    expect(clampPanelSize(301.6, PANEL_BOUNDS.right, 300)).toBe(302);
  });
});

describe("panels — resizeWithDelta", () => {
  it("applies delta in the given direction and clamps", () => {
    const r = PANEL_BOUNDS.right;
    expect(resizeWithDelta(300, 40, r, r.min, 1)).toBe(340);
    expect(resizeWithDelta(320, -40, r, r.min, 1)).toBe(r.min); // clamped low
    expect(resizeWithDelta(330, -50, r, r.min, -1)).toBe(380);
    expect(resizeWithDelta(470, 100, r, r.min, 1)).toBe(r.max); // clamped high
  });
});
