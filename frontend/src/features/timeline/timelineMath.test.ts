import { describe, expect, it } from "vitest";
import {
  clamp,
  clipDuration,
  formatTime,
  pxToSeconds,
  secondsToPx,
  shiftedClip,
  snapTime,
  trimLeft,
  trimRight,
} from "./timelineMath";

describe("timelineMath", () => {
  it("snaps to 0.1s", () => {
    expect(snapTime(1.23)).toBe(1.2);
    expect(snapTime(1.28)).toBe(1.3);
  });

  it("clamps", () => {
    expect(clamp(5, 0, 3)).toBe(3);
    expect(clamp(-1, 0, 3)).toBe(0);
  });

  it("converts px <-> seconds", () => {
    expect(secondsToPx(3, 80)).toBe(240);
    expect(pxToSeconds(240, 80)).toBe(3);
  });

  it("computes clip duration with a floor", () => {
    expect(clipDuration({ start_time: 1, end_time: 3 })).toBe(2);
    expect(clipDuration({ start_time: 1, end_time: 1.02 })).toBeGreaterThanOrEqual(0.1);
  });

  it("shifts a clip keeping its duration inside the timeline", () => {
    const moved = shiftedClip({ start_time: 1, end_time: 4 }, 2, 10);
    expect(moved.start_time).toBe(3);
    expect(moved.end_time).toBe(6);
    // cannot leave the timeline
    const clamped = shiftedClip({ start_time: 6, end_time: 8 }, 20, 10);
    expect(clamped.start_time).toBe(8);
    expect(clamped.end_time).toBe(10);
  });

  it("trims left/right without crossing the other edge", () => {
    const l = trimLeft({ start_time: 2, end_time: 5 }, 1);
    expect(l.start_time).toBe(3);
    expect(l.end_time).toBe(5);
    const r = trimRight({ start_time: 2, end_time: 5 }, 2);
    expect(r.end_time).toBe(7);
    // right cannot pass left + snap floor
    const r2 = trimRight({ start_time: 2, end_time: 5 }, -10);
    expect(r2.end_time).toBeGreaterThan(2);
  });

  it("formats ruler labels", () => {
    expect(formatTime(0)).toBe("0s");
    expect(formatTime(65)).toBe("1m05s");
    expect(formatTime(9)).toBe("9s");
  });
});
