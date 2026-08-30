// System Status Bar — 28px (DESIGN.md §4): provider / queue / connection status,
// identical position and height on every page. All values are real: WS health from
// the event socket, providers from GET /providers, queue size from the live
// generation store (transient state only).

import { useEffect, useState } from "react";
import { Circle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { ProviderStatus } from "../../api/types";
import { getSocketState, onSocketState, startEventSocket, type SocketState } from "../../events/socket";
import { useGenerationStore } from "../../stores/generationStore";

export function SystemStatusBar() {
  const [socketState, setSocketState] = useState<SocketState>(() => {
    // Mounting the status bar also guarantees the socket exists (idempotent).
    void startEventSocket();
    return getSocketState();
  });
  useEffect(() => onSocketState(setSocketState), []);

  const { data: providers } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: () => api.get<ProviderStatus[]>("/providers"),
    staleTime: 60_000,
  });

  const liveCount = useGenerationStore((state) => Object.keys(state.live).length);
  const activeProvider =
    providers?.find((item) => item.status === "active") ?? providers?.find((item) => item.status === "connected");

  return (
    <footer className="system-status-bar" role="status">
      <span className="status-cell ws-status" title={socketState === "connected" ? "事件通道已连接" : "事件通道未连接"}>
        <Circle
          size={8}
          weight="fill"
          className={`status-dot ${socketState === "connected" ? "ok" : socketState === "connecting" ? "warn" : "bad"}`}
        />
        {socketState === "connected" ? "已连接" : socketState === "connecting" ? "连接中" : "未连接"}
      </span>
      <span className="status-cell provider-status">
        Provider：{activeProvider?.name ?? (providers?.length ? "无激活" : "读取中")}
      </span>
      <span className="status-cell queue-status" title="进行中的生成任务（实时状态）">
        队列 {liveCount}
      </span>
      <span className="grow" />
      <span className="status-cell muted">Project State · SQLite</span>
    </footer>
  );
}
