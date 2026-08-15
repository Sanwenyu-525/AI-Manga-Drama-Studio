// P6-T008 Virtualized Shot Grid — a bounded, windowed render for large scenes.
//
// Approach (minimal + testable, roadmap 40): a sliding render window over the shot
// list. We only mount shots in [startIndex, endIndex):
//   - `startIndex` advances once the user scrolls past the top rows (drops leading
//     DOM nodes), driven by scrollTop on the shot grid's own scroll container.
//   - `endIndex` grows by `pageSize` toward the total via an IntersectionObserver
//     sentinel, so we never block mounting hundreds of shots up front.
// CSS additionally sets `content-visibility: auto` on each card (native culling) so
// even the mounted window pays little offscreen layout cost. Each card keeps its
// natural height, so the existing 20-shot visual behavior is unchanged.

import { useEffect, useRef, useState } from "react";
import { columnsForWidth, computeWindowList, growVisibleCount, windowStartFromScroll } from "../../lib/virtualization";

export interface VirtualizedGridOptions {
  /** Initial number of items mounted (the render window's opening size). */
  pageSize?: number;
  /** Rows kept beyond the viewport while scrolling. */
  overscan?: number;
  /** Keep at least this many items mounted ahead of the scroll position. */
  minKeep?: number;
  minCardWidth?: number;
  gap?: number;
  /** Estimated row height used purely for scroll→index math (px). */
  estimatedRowHeight?: number;
}

export interface VirtualizedGridResult {
  gridRef: React.RefObject<HTMLDivElement>;
  startIndex: number;
  endIndex: number;
  total: number;
  /** Call from onScroll; reports parsed col + scroll window to a callback if needed. */
  viewportHeight: number;
}

/** Hook returning the mounted [startIndex, endIndex) window for a shot list. */
export function useVirtualizedGrid(total: number, options: VirtualizedGridOptions = {}): VirtualizedGridResult {
  const {
    pageSize = 60,
    overscan = 2,
    minKeep = 120,
    minCardWidth = 160,
    gap = 18,
    estimatedRowHeight = 190,
  } = options;
  const gridRef = useRef<HTMLDivElement>(null);
  const [startIndex, setStartIndex] = useState(0);
  const [endIndex, setEndIndex] = useState(() => Math.min(total, pageSize));
  const [viewportHeight, setViewportHeight] = useState(600);


  useEffect(() => {
    const node = gridRef.current;
    if (!node) return;
    const measure = () => setViewportHeight(node.clientHeight || 600);
    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(node);
    return () => ro?.disconnect();
  }, []);

  const onScroll = () => {
    const node = gridRef.current;
    if (!node) return;
    const width = node.clientWidth || 800;
    const columns = columnsForWidth(width, minCardWidth, gap);
    const nextStart = windowStartFromScroll(node.scrollTop, viewportHeight, estimatedRowHeight, columns, minKeep);
    setStartIndex(nextStart);
    // Keep the tail ahead of the visible bottom unless everything is mounted.
    if (endIndex < total) {
      const win = computeWindowList(total, node.scrollTop, viewportHeight, estimatedRowHeight, columns, overscan);
      setEndIndex((cur) => Math.max(cur, growVisibleCount(total, win.endIndex, pageSize)));
    }
  };

  useEffect(() => {
    const node = gridRef.current;
    if (!node) return;
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => node.removeEventListener("scroll", onScroll);
  });

  return { gridRef, startIndex, endIndex, total, viewportHeight };
}