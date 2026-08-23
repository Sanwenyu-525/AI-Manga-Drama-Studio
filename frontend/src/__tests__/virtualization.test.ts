// P6-T008: virtualized shot grid — window math + incremental growth.
import { describe, expect, it } from "vitest";
import { columnsForWidth, computeWindowList, growVisibleCount, windowStartFromScroll } from "../lib/virtualization";

describe("virtualization — columnsForWidth", () => {
  it("computes columns from container width", () => {
    expect(columnsForWidth(800, 160, 18)).toBe(4); // (800+18)/(160+18)=4.59 → 4
    expect(columnsForWidth(160, 160, 18)).toBe(1);
    expect(columnsForWidth(0, 160, 18)).toBe(1);
    expect(columnsForWidth(NaN, 160, 18)).toBe(1);
  });
});

describe("virtualization — computeWindowList", () => {
  it("renders the full list when it fits the viewport", () => {
    const w = computeWindowList(8, 0, 600, 190, 4, 2);
    expect(w.startIndex).toBe(0);
    expect(w.endIndex).toBe(8);
  });
  it("mounts only a bounded slice for a large list at the top", () => {
    const w = computeWindowList(500, 0, 600, 190, 4, 2);
    expect(w.startIndex).toBe(0);
    expect(w.endIndex).toBeGreaterThan(0);
    expect(w.endIndex).toBeLessThan(500);
  });
  it("slides the window forward as the user scrolls", () => {
    const top = computeWindowList(500, 0, 600, 190, 4, 2);
    const scrolled = computeWindowList(500, 4000, 600, 190, 4, 2);
    expect(scrolled.startIndex).toBeGreaterThan(top.startIndex);
    expect(scrolled.startIndex).toBeLessThanOrEqual(scrolled.endIndex);
    expect(scrolled.endIndex).toBeLessThanOrEqual(500);
  });
  it("stays within bounds at the very bottom", () => {
    const w = computeWindowList(500, 100000, 600, 190, 4, 2);
    expect(w.startIndex).toBeLessThan(w.endIndex);
    expect(w.endIndex).toBe(500);
  });
  it("returns an empty window for zero items", () => {
    const w = computeWindowList(0, 0, 600, 190, 4, 2);
    expect(w).toEqual({ itemCount: 0, startIndex: 0, endIndex: 0 });
  });
  it("window size stays bounded (O(viewport)) regardless of list size", () => {
    const windowSize = (total: number) => {
      const w = computeWindowList(total, 0, 600, 190, 4, 2);
      return w.endIndex - w.startIndex;
    };
    expect(windowSize(60)).toBeLessThanOrEqual(windowSize(60));
    expect(windowSize(1000)).toBeLessThan(200);
    expect(windowSize(10000)).toBe(windowSize(1000));
  });
});

describe("virtualization — growVisibleCount", () => {
  it("grows by a page and clamps at the total", () => {
    expect(growVisibleCount(500, 60, 60)).toBe(120);
    expect(growVisibleCount(500, 480, 60)).toBe(500);
    expect(growVisibleCount(0, 0, 60)).toBe(0);
  });
});

describe("virtualization — windowStartFromScroll", () => {
  it("drops leading items once scrolled past them", () => {
    expect(windowStartFromScroll(0, 600, 190, 4, 120)).toBe(0);
    // keep 120 items = 30 rows ahead; scrolling well past that must drop leading items.
    const advanced = windowStartFromScroll(20000, 600, 190, 4, 120);
    expect(advanced).toBeGreaterThan(0);
    expect(advanced % 4).toBe(0); // aligned to a row
  });
});
