// P6-T008 Virtualized Shot Grid — windowing helpers (pure, unit-testable).
//
// Strategy (minimal + testable, per roadmap 40): native content-visibility:
// auto culling in CSS plus a bounded render window. We only mount shots inside a
// sliding [startIndex, endIndex) window: leading shots above the scroll position
// are dropped, and the trailing edge grows as the user scrolls toward it. This
// keeps the DOM node count O(viewport) for scenes with dozens-hundreds of shots
// while leaving every visible card's natural height (and thus the existing
// 20-shot visual behavior) untouched.

export interface WindowSpec {
  itemCount: number;
  /** First index currently mounted. */
  startIndex: number;
  /** One past the last mounted index. */
  endIndex: number;
}

/** Number of columns for a grid given the container width and a min card width.
 *  Used to turn a scroll offset into an item index window. */
export function columnsForWidth(width: number, minCardWidth: number, gap: number): number {
  if (!Number.isFinite(width) || width <= 0) return 1;
  return Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
}

/** Compute the render window for a scroll container.
 *  viewportHeight = visible px; overscan = extra rows kept on either side. */
export function computeWindowList(
  itemCount: number,
  scrollTop: number,
  viewportHeight: number,
  avgRowHeight: number,
  columns: number,
  overscan: number,
): WindowSpec {
  if (itemCount <= 0) return { itemCount: 0, startIndex: 0, endIndex: 0 };
  const col = Math.max(1, columns);
  const rowH = Math.max(1, avgRowHeight);
  const rowCount = Math.ceil(itemCount / col);
  // First/next-last *row* bounds, clamped so we always keep at least one row on
  // screen (even pinned to the very bottom).
  const firstRow = Math.max(0, Math.floor(scrollTop / rowH) - overscan);
  const rawLastRow = Math.ceil((scrollTop + viewportHeight) / rowH) + overscan;
  const lastRow = Math.min(rowCount, Math.max(firstRow + 1, rawLastRow));
  // Never drop the leading edge below the row before the last (keeps >=1 row on screen).
  const startRow = Math.min(firstRow, Math.max(0, lastRow - 1));
  const startIndex = Math.min(itemCount, startRow * col);
  const endIndex = Math.min(itemCount, lastRow * col);
  return { itemCount, startIndex, endIndex: Math.max(startIndex, endIndex) };
}

/** Incremental render helper: grow the visible count by a page once the user
 *  approaches the current tail, until every item is mounted. */
export function growVisibleCount(total: number, currentVisible: number, pageSize: number): number {
  if (total <= 0) return 0;
  return Math.min(total, currentVisible + Math.max(1, pageSize));
}

/** Slide window start forward as the user scrolls past items, keeping only the
 *  trailing page visible. Returns the clamped start index. */
export function windowStartFromScroll(
  scrollTop: number,
  _viewportHeight: number,
  avgRowHeight: number,
  columns: number,
  minKeep: number,
): number {
  const col = Math.max(1, columns);
  const keepRows = Math.ceil(minKeep / col);
  const startRow = Math.max(0, Math.floor(scrollTop / Math.max(1, avgRowHeight)) - keepRows);
  return startRow * col;
}
