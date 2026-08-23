// P6-T002: ResizeHandle — pointer-drag gesture reports deltas.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

afterEach(cleanup);
import { ResizeHandle } from "../components/resizable/ResizeHandle";

function pointerEventOf(node: Element, type: string, clientX: number) {
  return fireEvent(node, new PointerEvent(type, { bubbles: true, clientX, pointerId: 1 }));
}

describe("ResizeHandle", () => {
  it("reports the horizontal delta on drag", () => {
    const onDelta = vi.fn();
    const onDragEnd = vi.fn();
    const { getByRole } = render(
      <ResizeHandle axis="vertical" label="resize" onDelta={onDelta} onDragEnd={onDragEnd} />,
    );
    const handle = getByRole("separator");
    // pointerdown captures the start X; moves report clientX - startX.
    if (!(handle as HTMLElement).setPointerCapture) {
      (handle as HTMLElement).setPointerCapture = () => {};
      (handle as HTMLElement).releasePointerCapture = () => {};
    }
    pointerEventOf(handle, "pointerdown", 300);
    pointerEventOf(handle, "pointermove", 340);
    pointerEventOf(handle, "pointerup", 355);
    expect(onDelta).toHaveBeenCalledWith(40);
    expect(onDragEnd).toHaveBeenCalledTimes(1);
  });
  it("ignores moves until pointerdown (not dragging)", () => {
    const onDelta = vi.fn();
    const { getByRole } = render(<ResizeHandle axis="horizontal" label="resize" onDelta={onDelta} />);
    const handle = getByRole("separator");
    pointerEventOf(handle, "pointermove", 500);
    expect(onDelta).not.toHaveBeenCalled();
  });
  it("does not start dragging when disabled", () => {
    const onDelta = vi.fn();
    const { getByRole } = render(<ResizeHandle axis="vertical" label="resize" onDelta={onDelta} disabled />);
    const handle = getByRole("separator");
    expect(handle.getAttribute("aria-disabled")).toBe("true");
    pointerEventOf(handle, "pointerdown", 300);
    pointerEventOf(handle, "pointermove", 340);
    expect(onDelta).not.toHaveBeenCalled();
  });
});
