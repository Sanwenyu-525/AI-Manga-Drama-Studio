// P8-T020 — Shot Inspector continuity panel (frontend-ux §77, §47, §79):
// per-shot continuity-state card with start/end summaries (角色/环境/道具, Chinese labels,
// — when empty) plus the shared warning list with acknowledge + AI-fix actions.

import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { ContinuityShotReadCard } from "../../api/types";
import { ContinuityWarningList } from "./ContinuityWarningList";

export function ShotContinuityCard({ shotId }: { shotId: string }) {
  const sceneId = useQuery({
    queryKey: queryKeys.shot(shotId),
    queryFn: () => api.get<{ scene_id: string }>(`/shots/${shotId}`),
    enabled: !!shotId,
  }).data?.scene_id;

  const { data: card, isLoading } = useQuery({
    queryKey: queryKeys.shotContinuity(shotId),
    queryFn: () => api.get<ContinuityShotReadCard>(`/shots/${shotId}/continuity-state`),
    enabled: !!shotId,
  });

  if (isLoading && !card) {
    return (
      <div className="continuity-card">
        <p className="muted small">正在读取连续性状态…</p>
      </div>
    );
  }
  if (!card) return null;
  const start = card.start_state ?? null;
  const end = card.end_state ?? null;
  const warnings = card.warnings ?? [];

  return (
    <div className="continuity-card">
      <div className="continuity-card-title">
        <span>连续性状态</span>
        <span className="muted small">{card.state_hash ? `#${card.state_hash.slice(0, 8)}` : ""}</span>
      </div>

      <div className="continuity-state-columns">
        <StateColumn title="起始" state={start} />
        <StateColumn title="结束" state={end} />
      </div>

      {warnings.length > 0 ? (
        <ContinuityWarningList warnings={warnings} sceneId={sceneId ?? ""} showFix />
      ) : (
        <p className="muted small continuity-none">镜间状态一致，无连续性警告。</p>
      )}
    </div>
  );
}

function StateColumn({ title, state }: { title: string; state: ContinuityShotReadCard["start_state"] }) {
  return (
    <div className="continuity-state-column">
      <div className="continuity-state-column-title">{title}</div>
      {state ? (
        <>
          <CharacterStateSummary state={state} />
          <EnvStateSummary state={state} />
          <PropStateSummary state={state} />
          {!state.characters && !state.environment && !state.props && <p className="muted small">—</p>}
        </>
      ) : (
        <p className="muted small">—</p>
      )}
    </div>
  );
}

function CharacterStateSummary({ state }: { state: ContinuityShotReadCard["start_state"] }) {
  const chars = state?.characters;
  if (!chars) return null;
  const list: Array<Record<string, unknown>> = Array.isArray(chars)
    ? (chars as Array<Record<string, unknown>>)
    : Object.values(chars as Record<string, Record<string, unknown>>);
  if (list.length === 0) return null;
  return (
    <div className="continuity-state-group characters">
      <div className="continuity-state-group-title">角色</div>
      {list.map((c, idx) => {
        const rows: Array<[string, unknown]> = (
          [
            ["版本", c.character_version_id],
            ["服装", c.costume_id],
            ["位置", c.position],
            ["动作", c.action],
            ["情绪", c.emotion],
          ] as Array<[string, unknown]>
        ).filter(([, v]) => v !== null && v !== undefined && v !== "");
        return (
          <div key={idx} className="continuity-char">
            <div className="continuity-char-name">{String(c.character_id ?? c.name ?? "角色")}</div>
            {rows.map(([k, v], i) => (
              <div key={i} className="continuity-state-item">
                <span>{k}</span>
                <strong>{String(v)}</strong>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function EnvStateSummary({ state }: { state: ContinuityShotReadCard["start_state"] }) {
  const env = state?.environment;
  if (!env) return null;
  const items = [
    ["地点", env.location_id],
    ["时段", env.time_of_day],
    ["灯光", env.lighting],
    ["天气", env.weather],
    ["氛围", env.mood],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "") as Array<[string, unknown]>;
  if (items.length === 0) return null;
  return (
    <div className="continuity-state-group">
      <div className="continuity-state-group-title">环境</div>
      {items.map(([k, v], idx) => (
        <div key={idx} className="continuity-state-item">
          <span>{k}</span>
          <strong>{String(v)}</strong>
        </div>
      ))}
    </div>
  );
}

function PropStateSummary({ state }: { state: ContinuityShotReadCard["start_state"] }) {
  const props = state?.props;
  if (!props) return null;
  const list: Array<Record<string, unknown>> = Array.isArray(props)
    ? (props as Array<Record<string, unknown>>)
    : Object.values(props as Record<string, Record<string, unknown>>);
  if (list.length === 0) return null;
  return (
    <div className="continuity-state-group">
      <div className="continuity-state-group-title">道具</div>
      {list.map((p, idx) => (
        <div key={idx} className="continuity-state-item">
          <span>{String(p.prop_id ?? "道具")}</span>
          <strong>
            {p.visible === false ? "不可见" : "可见"}
            {p.holder_character_id ? ` · 持有者 ${p.holder_character_id}` : ""}
          </strong>
        </div>
      ))}
    </div>
  );
}
