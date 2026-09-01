// P6-T008: VirtualizedShotGrid — renders the full small grid but only a bounded
// window for large scenes.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

afterEach(cleanup);
import { VirtualizedShotGrid } from "../features/storyboard/VirtualizedShotGrid";

function makeShots(n: number) {
  return Array.from(
    { length: n },
    (_, i) =>
      ({
        id: `shot_${i}`,
        shot_number: i + 1,
        shot_type: "medium",
        status: "draft",
        dirty_state: "clean",
        character_names: [],
        thumbnail_url: null,
      }) as never,
  );
}

describe("VirtualizedShotGrid", () => {
  it("renders every shot for a small scene (existing 20-shot behavior)", () => {
    const shots = makeShots(20) as never[];
    render(<VirtualizedShotGrid shots={shots} onSelect={() => {}} />);
    // The plain grid renders all 20 cards.
    expect(document.querySelectorAll(".shot-card").length).toBe(20);
  });
  it("renders only a bounded window for a large scene", () => {
    const shots = makeShots(300) as never[];
    render(<VirtualizedShotGrid shots={shots} onSelect={() => {}} />);
    const rendered = document.querySelectorAll(".shot-card").length;
    expect(rendered).toBeLessThan(300);
    expect(rendered).toBeGreaterThan(0);
  });
  it("invokes onSelect when a card is clicked", () => {
    const onSelect = vi.fn();
    const shots = makeShots(10) as never[];
    render(<VirtualizedShotGrid shots={shots} selectedShotId="shot_3" onSelect={onSelect} />);
    const cards = Array.from(document.querySelectorAll(".shot-card")) as HTMLElement[];
    const card = cards.find((c) => c.textContent?.includes("Shot 004"));
    expect(card).toBeTruthy();
    card!.click();
    expect(onSelect).toHaveBeenCalledWith("shot_3");
  });

  it("passes toggle/shift modifiers on modifier-clicks (iteration-02)", () => {
    const onSelect = vi.fn();
    const shots = makeShots(4) as never[];
    render(<VirtualizedShotGrid shots={shots} onSelect={onSelect} />);
    const card = (Array.from(document.querySelectorAll(".shot-card")) as HTMLElement[])[2];
    card!.dispatchEvent(new MouseEvent("click", { bubbles: true, ctrlKey: true }));
    expect(onSelect).toHaveBeenLastCalledWith("shot_2", { toggle: true, shift: false });
    card!.dispatchEvent(new MouseEvent("click", { bubbles: true, shiftKey: true }));
    expect(onSelect).toHaveBeenLastCalledWith("shot_2", { toggle: false, shift: true });
  });

  it("renders and toggles multi-select checkboxes (iteration-02)", () => {
    const onSelect = vi.fn();
    const onToggleSelect = vi.fn();
    const shots = makeShots(4) as never[];
    render(
      <VirtualizedShotGrid
        shots={shots}
        onSelect={onSelect}
        multiSelectedIds={["shot_1"]}
        onToggleSelect={onToggleSelect}
      />,
    );
    const checks = Array.from(document.querySelectorAll(".shot-select-check")) as HTMLElement[];
    expect(checks.length).toBe(4);
    const checked = checks.find((el) => el.getAttribute("aria-checked") === "true");
    expect(checked?.getAttribute("aria-label")).toContain("Shot 002");

    // Clicking the checkbox toggles without triggering card single-select.
    checks[3].click();
    expect(onToggleSelect).toHaveBeenCalledWith("shot_3");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("hides checkboxes when multi-select is not enabled", () => {
    const shots = makeShots(4) as never[];
    render(<VirtualizedShotGrid shots={shots} onSelect={() => {}} />);
    expect(document.querySelectorAll(".shot-select-check").length).toBe(0);
  });
});
