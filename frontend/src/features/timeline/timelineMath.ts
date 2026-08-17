// Pure timeline math (Phase 9) — unit-testable drag/trim/snap/format helpers.

export const DEFAULT_CLIP_DURATION = 3;
export const SNAP_STEP = 0.1;

/** Round a time to the timeline snap step (0.1s). */
export function snapTime(t: number): number {
  // round via toFixed to avoid float drift (0.1 * 12 !== 1.2 cleanly)
  const snapped = Math.round(t / SNAP_STEP) * SNAP_STEP;
  return Number(snapped.toFixed(3));
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** seconds → CSS px at the given scale. */
export function secondsToPx(seconds: number, pxPerSecond: number): number {
  return seconds * pxPerSecond;
}

/** px → seconds at the given scale. */
export function pxToSeconds(px: number, pxPerSecond: number): number {
  return px / Math.max(pxPerSecond, 1);
}

/** Duration of a clip (guard against invalid/zero). */
export function clipDuration(clip: { start_time: number; end_time: number }): number {
  return Math.max(clip.end_time - clip.start_time, SNAP_STEP);
}

/** New [start, end] after a horizontal drag by deltaSeconds; keeps duration and
 *  stays inside [0, timelineDuration]. */
export function shiftedClip(
  clip: { start_time: number; end_time: number },
  deltaSeconds: number,
  timelineDuration: number,
  min: number = 0,
): { start_time: number; end_time: number } {
  const duration = clipDuration(clip);
  const start = clamp(snapTime(clip.start_time + deltaSeconds), min, Math.max(min, timelineDuration - duration));
  return { start_time: start, end_time: Math.min(timelineDuration, start + duration) };
}

/** New [start, end] after trimming the LEFT edge by deltaSeconds (max duration
 *  growth is the clip's full length; floor at SNAP_STEP). */
export function trimLeft(
  clip: { start_time: number; end_time: number },
  deltaSeconds: number,
): { start_time: number; end_time: number } {
  let start = snapTime(clip.start_time + deltaSeconds);
  start = clamp(start, 0, clip.end_time - SNAP_STEP);
  return { start_time: start, end_time: clip.end_time };
}

/** Trim RIGHT edge: the new boundary may not go below start + SNAP_STEP. */
export function trimRight(
  clip: { start_time: number; end_time: number },
  deltaSeconds: number,
): { start_time: number; end_time: number } {
  let end = snapTime(clip.end_time + deltaSeconds);
  end = clamp(end, clip.start_time + SNAP_STEP, Number.MAX_SAFE_INTEGER);
  return { start_time: clip.start_time, end_time: end };
}

/** "0.5s" / "1m 23s" style label for the ruler. */
export function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const s = total % 60;
  const m = Math.floor(total / 60);
  return m > 0 ? `${m}m${s.toString().padStart(2, "0")}s` : `${total}s`;
}

/** Overlap check: two time ranges intersect (excluding point-touch). */
export function overlaps(a: { start_time: number; end_time: number }, b: { start_time: number; end_time: number }): boolean {
  return a.start_time < b.end_time && b.start_time < a.end_time;
}