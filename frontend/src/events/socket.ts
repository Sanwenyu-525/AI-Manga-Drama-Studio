// WebSocket event layer (frontend-ux §83, api-event-contract §74-77):
// EventSocket → EventRouter → handlers. High-frequency events (generation.progress)
// update the store directly; resource events invalidate TanStack queries.

import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../api/queryKeys";
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
      if (event.event_type === "system.connected") {
        lastSequence = event.sequence;
        return;
      }
      if (event.sequence <= lastSequence) return; // dedupe (contract §52)
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
    switch (event.event_type) {
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
