// P1-E6-T01: event reconcile gate — sequence dedupe + malformed-envelope handling
// (api-event-contract §52, §137).
// P1-E4-T02: classifySequence adds the "gap" verdict — a jumped sequence means
// events were lost and the client must reconcile from REST (observable recovery).
import { describe, expect, it, vi } from "vitest";
import { classifySequence, isWellFormedEvent, setReconcileHandler } from "../events/socket";

describe("classifySequence", () => {
  it("routes contiguous newer sequences", () => {
    expect(classifySequence(5, 4)).toBe("route");
    expect(classifySequence(1, 0)).toBe("route"); // first event after system.connected
  });

  it("flags duplicates and stale/out-of-order sequences", () => {
    expect(classifySequence(4, 4)).toBe("dupe");
    expect(classifySequence(3, 4)).toBe("dupe"); // stale (out of order)
  });

  it("flags gaps (lost events) for reconcile instead of silently routing", () => {
    expect(classifySequence(6, 4)).toBe("gap");
    expect(classifySequence(100, 4)).toBe("gap");
  });
});

describe("setReconcileHandler", () => {
  it("invokes the handler (observable recovery hook)", async () => {
    const { reconcile } = await import("../events/socket");
    const handler = vi.fn();
    setReconcileHandler(handler);
    try {
      reconcile("unit-test");
      expect(handler).toHaveBeenCalledWith("unit-test");
    } finally {
      setReconcileHandler(null);
    }
  });
});

describe("isWellFormedEvent", () => {
  it("accepts a valid envelope", () => {
    expect(
      isWellFormedEvent({
        event_id: "e1",
        event_type: "shot.updated",
        sequence: 1,
        timestamp: "t",
        project_id: null,
        entity_type: "shot",
        entity_id: "s1",
        event_version: 1,
        payload: {},
      }),
    ).toBe(true);
  });

  it("rejects malformed payloads (unknown-version / garbage)", () => {
    expect(isWellFormedEvent(null)).toBe(false);
    expect(isWellFormedEvent({})).toBe(false);
    expect(isWellFormedEvent({ event_type: "shot.updated" })).toBe(false); // missing sequence
    expect(isWellFormedEvent({ event_id: "e", event_type: "x", sequence: "1", timestamp: "t" })).toBe(false); // wrong types
  });
});
