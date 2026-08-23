// P6-T002 Resizable Panels — pure geometry helpers (unit-testable, no DOM).
// Panel width/height constraints come from frontend-ux-design §90:
//   Left 200–400px · Right 280–480px · Bottom 150–500px

export interface PanelBounds {
  min: number;
  max: number;
}

export const PANEL_BOUNDS = {
  explorer: { min: 200, max: 400 } as PanelBounds,
  right: { min: 280, max: 480 } as PanelBounds,
  bottom: { min: 150, max: 500 } as PanelBounds,
} as const;

export type PanelId = "explorer" | "right" | "bottom";

/** Clamp a raw pixel size into [min, max]; falls back to a sane default for NaN. */
export function clampPanelSize(raw: number, bounds: PanelBounds, fallback: number): number {
  const value = Number.isFinite(raw) ? raw : fallback;
  return Math.min(bounds.max, Math.max(bounds.min, Math.round(value)));
}

/** Compute the new panel size after a pointer drag delta along the resize axis. */
export function resizeWithDelta(
  startSize: number,
  delta: number,
  bounds: PanelBounds,
  fallback: number,
  dir: 1 | -1 = 1,
): number {
  return clampPanelSize(startSize + delta * dir, bounds, fallback);
}

/** Vertical (left/right panel) — each panel clamps independently; the flexible
 *  middle column absorbs the size change, so the other panel is left untouched. */
export function applyVerticalResize(
  which: "left" | "right",
  startLeft: number,
  startRight: number,
  delta: number,
): { explorerWidth: number; rightWidth: number } {
  if (which === "left") {
    return {
      explorerWidth: clampPanelSize(startLeft + delta, PANEL_BOUNDS.explorer, PANEL_BOUNDS.explorer.min),
      rightWidth: startRight,
    };
  }
  return {
    explorerWidth: startLeft,
    rightWidth: clampPanelSize(startRight - delta, PANEL_BOUNDS.right, PANEL_BOUNDS.right.min),
  };
}
