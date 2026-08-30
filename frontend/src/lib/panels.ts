// P6-T002 Resizable Panels — pure geometry helpers (unit-testable, no DOM).
// Panel width/height constraints: Right 280–480px · Bottom 150–220px
// (expanded drawer cap — the production desk keeps the canvas dominant; the
// collapsed 30px rail state is handled by the shell CSS).

export interface PanelBounds {
  min: number;
  max: number;
}

export const PANEL_BOUNDS = {
  right: { min: 280, max: 480 } as PanelBounds,
  bottom: { min: 150, max: 220 } as PanelBounds,
} as const;

export type PanelId = "right" | "bottom";

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
