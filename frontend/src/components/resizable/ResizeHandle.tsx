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
  /** Called with the incremental pixel delta from the drag start on each move. */
  onDelta: (delta: number) => void;
  /** Called once when a drag ends (for e.g. a debounced persist flush). */
  onDragEnd?: () => void;
  disabled?: boolean;
  /** v2 renders on the right gutter (between workspace and right-panel). */
  variant?: "default" | "right";
}

export function ResizeHandle({ axis, label, onDelta, onDragEnd, disabled, variant = "default" }: ResizeHandleProps) {
  const startRef = useRef(0);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (disabled) return;
      event.preventDefault();
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      startRef.current = axis === "vertical" ? event.clientX : event.clientY;
      setDragging(true);
    },
    [axis, disabled],
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

  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation={axis === "vertical" ? "vertical" : "horizontal"}
      aria-disabled={disabled || undefined}
      className={`resize-handle resize-handle--${axis}${variant === "right" ? " resize-handle--v2" : ""}${dragging ? " is-dragging" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stop}
      onPointerCancel={stop}
    />
  );
}