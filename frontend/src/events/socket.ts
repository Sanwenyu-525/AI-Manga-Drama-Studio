// WebSocket event layer (frontend-ux §83, api-event-contract §74-77):
// EventSocket → EventRouter → handlers. High-frequency events (generation.progress)
// update the store directly; resource events invalidate TanStack queries.

import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../api/queryKeys";
import { useAgentStore } from "../stores/agentStore";
import { useGenerationStore } from "../stores/generationStore";

export interface StudioEvent {
  event_id: string;
  event_type: string;
  event_version: number;
  project_id: string | null;
  entity_type: string;
  entity_id: string;
  timestamp: string;
  sequence: number;
  payload: Record<string, unknown>;
}

// Event gate (P1-E6-T01 / api-event-contract §52): pure sequence/dedupe/reconcile
// logic, extracted from the socket so it is unit-testable.
// Returns true when the event should be routed (newer sequence than seen).
export function shouldRouteEvent(sequence: number, lastSequence: number): boolean {
  return sequence > lastSequence;
}

// Returns true when the payload is a well-formed Studio event envelope.
export function isWellFormedEvent(value: unknown): value is StudioEvent {
  if (typeof value !== "object" || value === null) return false;
  const event = value as Record<string, unknown>;
  return (
    typeof event.event_id === "string" &&
    typeof event.event_type === "string" &&
    typeof event.sequence === "number" &&
    typeof event.timestamp === "string"
  );
}


const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/api/v1/events`;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

let socket: WebSocket | null = null;
let reconnectDelay = RECONNECT_BASE_MS;
let lastSequence = 0;

function connect() {
  socket = new WebSocket(WS_URL);
  socket.onopen = () => {
    reconnectDelay = RECONNECT_BASE_MS;
  };
  socket.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data as string) as StudioEvent;
      if (!isWellFormedEvent(event)) return; // malformed: ignore (contract §137)
      if (event.event_type === "system.connected") {
        lastSequence = event.sequence;
        return;
      }
      if (!shouldRouteEvent(event.sequence, lastSequence)) return; // dedupe (contract §52)
      lastSequence = event.sequence;
      routeEvent(event);
    } catch {
      // malformed event: ignore rather than crash the UI (contract §137)
    }
  };
  socket.onclose = () => {
    window.setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS); // backoff §76
  };
}

// Router: never write hundreds of ifs in onmessage (contract §74).
function routeEvent(event: StudioEvent) {
  const router = getRouter();
  router?.handle(event);
}

let routerRef: EventRouter | null = null;

export function setEventRouter(router: EventRouter | null) {
  routerRef = router;
}

function getRouter(): EventRouter | null {
  return routerRef;
}

export class EventRouter {
  constructor(private queryClient: ReturnType<typeof useQueryClient>) {}

  handle(event: StudioEvent): void {
    const generation = useGenerationStore.getState();
    const agent = useAgentStore.getState();
    switch (event.event_type) {
      // ---- agent events → agentStore (AI Command Center, frontend-ux §15-21) ----
      case "agent.run.started":
        break; // start handled at submit time (run_id returned synchronously)
      case "agent.plan.created": {
        const plan = event.payload.plan as
          | { objective?: string; steps?: Array<{ tool: string; arguments: Record<string, unknown> }> }
          | undefined;
        if (plan) {
          agent.setPlan(
            plan.objective ?? "",
            (plan.steps ?? []).map((step) => ({ tool: step.tool, args: step.arguments ?? {} })),
          );
        }
        break;
      }
      case "agent.tool.started":
        agent.toolStarted(
          event.payload.tool as string,
          ((event.payload.target as { id?: string } | undefined)?.id) as string | undefined,
        );
        break;
      case "agent.tool.completed":
        agent.toolCompleted(
          event.payload.tool as string,
          Boolean(event.payload.success),
          (event.payload.changed_fields as string[] | undefined) ?? [],
          event.payload.error as string | undefined,
        );
        break;
      case "agent.run.completed":
        agent.runCompleted(event.payload.result as Record<string, unknown> | null);
        void this.queryClient.invalidateQueries({ queryKey: ["shots"] });
        void this.queryClient.invalidateQueries({ queryKey: ["storyboard"] });
        break;
      case "agent.run.failed":
        agent.runFailed(event.payload.error as string | undefined);
        break;
      case "agent.run.cancelled":
        agent.runFailed("已取消");
        break;

      // ---- generation events (contract §64-67) ----
      case "generation.queued":
      case "generation.started":
      case "generation.retrying":
        generation.upsert({
          id: event.entity_id,
          shotId: (event.payload.shot_id as string) ?? null,
          progress: 0,
          stage: event.payload.stage as string | null,
          status: event.event_type.replace("generation.", ""),
        });
        break;
      case "generation.progress":
        generation.upsert({
          id: event.entity_id,
          shotId: (event.payload.shot_id as string) ?? null,
          progress: (event.payload.progress as number) ?? 0,
          stage: event.payload.stage as string | null,
          status: "running",
        });
        break;
      case "generation.completed":
      case "generation.failed":
      case "generation.cancelled":
        generation.remove(event.entity_id);
        this.refreshAfterGeneration();
        break;
      case "asset.created":
        void this.queryClient.invalidateQueries({ queryKey: queryKeys.projects });
        break;
      case "shot.updated":
      case "shot.active_version.changed":
        if (event.project_id) {
          void this.queryClient.invalidateQueries({ queryKey: ["storyboard"] });
          void this.queryClient.invalidateQueries({ queryKey: ["shots"] });
        }
        break;
      case "character.created":
      case "character.updated":
      case "character.deleted":
        if (event.project_id) {
          void this.queryClient.invalidateQueries({ queryKey: queryKeys.characters(event.project_id) });
        }
        break;
      // ---- P6-T022/023/024: job events → invalidate job list + detail queries ----
      // The event envelope's project_id (when present) targets that project's list;
      // detail rows are invalidated by prefix so recoverable status changes surface.
      case "job.created":
      case "job.updated":
      case "job.completed":
      case "job.failed":
      case "job.cancelled":
      case "job.paused":
      case "job.resumed":
      case "job.task.updated":
        if (event.project_id) {
          void this.queryClient.invalidateQueries({ queryKey: queryKeys.jobs(event.project_id) });
        }
        void this.queryClient.invalidateQueries({ queryKey: ["jobs"] });
        void this.queryClient.invalidateQueries({ queryKey: ["job"] });
        break;
      case "scene.created":
        void this.queryClient.invalidateQueries({ queryKey: ["scenes"] });
        break;
      default:
        break;
    }
  }

  private refreshAfterGeneration(): void {
    void this.queryClient.invalidateQueries({ queryKey: ["storyboard"] });
    void this.queryClient.invalidateQueries({ queryKey: ["shots"] });
    void this.queryClient.invalidateQueries({ queryKey: ["generations"] });
    void this.queryClient.invalidateQueries({ queryKey: ["versions"] });
  }
}

export function startEventSocket(): void {
  if (socket) return;
  connect();
}
