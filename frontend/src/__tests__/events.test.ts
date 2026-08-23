// P1-E6-T01: event reconcile gate — sequence dedupe + malformed-envelope handling
// (api-event-contract §52, §137).
import { describe, expect, it } from "vitest";
import { isWellFormedEvent, shouldRouteEvent } from "../events/socket";

describe("shouldRouteEvent", () => {
  it("routes newer sequences and drops stale/duplicate ones", () => {
    expect(shouldRouteEvent(5, 4)).toBe(true);
    expect(shouldRouteEvent(4, 4)).toBe(false); // duplicate
    expect(shouldRouteEvent(3, 4)).toBe(false); // stale (out of order)
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
