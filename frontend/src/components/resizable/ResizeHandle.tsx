// P6-T002 Resizable Panel handle — native pointer-event drag resizing (no deps).
// The handle captures the pointer, reports a normalized delta to `onDelta`, and
// releases on pointerup. Geometry/clamping lives in `../lib/panels` so it is unit
// testable; this component only manages the drag gesture.

import { useCallback, useRef, useState } from "react";

export type ResizeAxis = "vertical" | "horizontal";

interface ResizeHandleProps {
  /** vertical = left/right panels (drag horizontally); horizontal = bottom dock (drag vertically). */
  axis: ResizeAxis;
  /** Human-label for aria (e.g. "调整左侧面板宽度"). */
  label: string;
  /** Called with the cumulative pixel delta from the drag start on each move. */
  onDelta: (delta: number) => void;
  /** Called once at pointerdown so the consumer can snapshot the baseline size
   *  BEFORE it starts changing (onDelta is cumulative, so the baseline must stay
   *  frozen for the whole gesture — a per-render baseline doubles the delta). */
  onDragStart?: () => void;
  /** Called once when a drag ends (for e.g. a debounced persist flush). */
  onDragEnd?: () => void;
  disabled?: boolean;
  /** edge renders as an invisible strip over a panel boundary line (the line itself is the handle). */
  variant?: "default" | "edge";
}

export function ResizeHandle({
  axis,
  label,
  onDelta,
  onDragStart,
  onDragEnd,
  disabled,
  variant = "default",
}: ResizeHandleProps) {
  const startRef = useRef(0);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (disabled) return;
      event.preventDefault();
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      startRef.current = axis === "vertical" ? event.clientX : event.clientY;
      onDragStart?.();
      setDragging(true);
    },
    [axis, disabled, onDragStart],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      const current = axis === "vertical" ? event.clientX : event.clientY;
      onDelta(current - startRef.current);
    },
    [axis, dragging, onDelta],
  );

  const stop = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      setDragging(false);
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        /* pointer may already be released */
      }
      onDragEnd?.();
    },
    [dragging, onDragEnd],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (disabled) return;
      const positive = axis === "vertical" ? event.key === "ArrowRight" : event.key === "ArrowDown";
      const negative = axis === "vertical" ? event.key === "ArrowLeft" : event.key === "ArrowUp";
      if (!positive && !negative) return;
      event.preventDefault();
      onDragStart?.();
      onDelta(positive ? 16 : -16);
      onDragEnd?.();
    },
    [axis, disabled, onDelta, onDragStart, onDragEnd],
  );

  return (
    <div
      role="separator"
      tabIndex={disabled ? -1 : 0}
      aria-label={label}
      aria-orientation={axis === "vertical" ? "vertical" : "horizontal"}
      aria-disabled={disabled || undefined}
      className={`resize-handle resize-handle--${axis}${variant === "edge" ? " resize-handle--edge" : ""}${dragging ? " is-dragging" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stop}
      onPointerCancel={stop}
      onKeyDown={onKeyDown}
    />
  );
}
