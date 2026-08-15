// P6-T008: VirtualizedShotGrid — renders the full small grid but only a bounded
// window for large scenes.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

afterEach(cleanup);
import { VirtualizedShotGrid } from "../features/storyboard/VirtualizedShotGrid";

function makeShots(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: `shot_${i}`,
    shot_number: i + 1,
    shot_type: "medium",
    status: "draft",
    dirty_state: "clean",
    character_names: [],
    thumbnail_url: null,
  } as never));
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
});