// P6-T008 Virtualized Shot Grid — windowed card rendering for the Storyboard.
// Small scenes (<= pageSize shots, incl. the existing 20-shot case) render exactly
// as before — full grid, no virtualization. Large scenes mount only a bounded
// [startIndex, endIndex) window so per-card markup stays identical and layout
// stays stable while scrolling.

import { MagicWand } from "@phosphor-icons/react";
import type { Shot, ShotSummary } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { ShotThumbImage } from "./ShotThumbImage";
import { useVirtualizedGrid } from "./useVirtualizedGrid";

/** Common camera-movement values → production-desk labels (free-form fallback). */
const CAMERA_MOVEMENT_LABELS: Record<string, string> = {
  static: "固定机位",
  handheld: "手持感",
  dolly: "缓慢推进",
  dolly_in: "缓慢推进",
  push_in: "缓慢推进",
  dolly_out: "缓慢拉远",
  pull_out: "缓慢拉远",
  pan: "横摇",
  pan_left: "左横摇",
  pan_right: "右横摇",
  tilt: "俯仰",
  tracking: "跟拍",
  follow: "跟拍",
  crane: "升降",
  zoom: "变焦",
};

type ShotCardDetail = Pick<Shot, "action" | "camera_angle" | "camera_movement" | "emotion" | "dialogue">;

interface VirtualizedShotGridProps {
  shots: ShotSummary[];
  /** Full shot records keyed by id (GET /scenes/{id}/shots) — real description + camera language. */
  details?: Record<string, ShotCardDetail>;
  selectedShotId?: string;
  onSelect: (shotId: string) => void;
  /** Open the shot in a center Editor Tab (double-click). */
  onOpenShot?: (shot: ShotSummary) => void;
  /** Threshold below which we render everything (no virtualization). */
  pageSize?: number;
}

export function VirtualizedShotGrid({
  shots,
  details,
  selectedShotId,
  onSelect,
  onOpenShot,
  pageSize = 60,
}: VirtualizedShotGridProps) {
  const small = shots.length <= pageSize;
  const virtual = useVirtualizedGrid(shots.length, { pageSize });
  const { startIndex, endIndex, gridRef } = virtual;

  if (small || endIndex <= startIndex) {
    // Small scenes (≤9 shots) cap at 3 columns so a nine-shot scene reads as a
    // 3×3 board; larger scenes keep the responsive auto-fill density.
    const fewClass = shots.length <= 9 ? " shot-grid--few" : "";
    return (
      <div className={`shot-grid shot-grid--plain${fewClass}`}>
        {shots.map((shot, i) => renderCard(shot, details, selectedShotId, onSelect, onOpenShot, i))}
      </div>
    );
  }

  const visible = shots.slice(startIndex, endIndex);
  return (
    <div
      ref={gridRef}
      className="shot-grid-scroll"
      data-testid="shot-grid-scroll"
      data-window={`${startIndex}-${endIndex}`}
    >
      <div className="shot-grid shot-grid--virtual">
        {visible.map((shot, i) => renderCard(shot, details, selectedShotId, onSelect, onOpenShot, startIndex + i))}
      </div>
      {endIndex < shots.length && (
        <div className="shot-grid-sentinel" data-testid="shot-grid-sentinel">
          已加载 {endIndex}/{shots.length} 个镜头 · 滚动加载更多
        </div>
      )}
    </div>
  );
}

function cameraLabel(detail?: ShotCardDetail, shotType?: string): string {
  const type = SHOT_TYPE_LABELS[shotType ?? ""] ?? shotType ?? "镜头";
  const movement = detail?.camera_movement?.trim();
  const angle = detail?.camera_angle?.trim();
  const suffix = movement
    ? (CAMERA_MOVEMENT_LABELS[movement.toLowerCase()] ?? movement)
    : angle
      ? angle
      : null;
  return suffix ? `${type} · ${suffix}` : type;
}

function renderCard(
  shot: ShotSummary,
  details: Record<string, ShotCardDetail> | undefined,
  selectedShotId: string | undefined,
  onSelect: (id: string) => void,
  onOpenShot: ((shot: ShotSummary) => void) | undefined,
  key: number,
) {
  const isSelected = selectedShotId === shot.id;
  const isGenerating = shot.active_generation && typeof shot.active_generation === "object";
  const progress = isGenerating && typeof shot.active_generation?.progress === "number" ? shot.active_generation.progress : null;
  const detail = details?.[shot.id];
  const description = detail?.action?.trim();
  return (
    <button
      key={key}
      type="button"
      className={`shot-card ${isSelected ? "selected" : ""} ${shot.status === "failed" ? "failed" : ""}`}
      onClick={() => onSelect(shot.id)}
      onDoubleClick={() => onOpenShot?.(shot)}
    >
      <div className="shot-thumb">
        <ShotThumbImage shot={shot} />
        {isGenerating && (
          <div className="shot-generating">
            <MagicWand size={18} /> 生成中{progress != null ? ` ${progress}%` : ""}
          </div>
        )}
      </div>
      <div className="shot-card-body">
        <div className="shot-meta">
          <span className="shot-number">
            SH{String(shot.shot_number).padStart(2, "0")}
            <span className="shot-number-legacy">Shot {String(shot.shot_number).padStart(3, "0")}</span>
          </span>
          <span className="shot-duration">{shot.duration != null ? `${shot.duration.toFixed(1)}s` : "—"}</span>
        </div>
        <div className="shot-camera-label">{cameraLabel(detail, shot.shot_type)}</div>
        <p className="shot-description">
          {description ?? (shot.character_names.length ? `${shot.character_names.join("、")} · 画面描述待编辑` : "画面描述待编辑")}
        </p>
        <div className="shot-cast-line">
          {shot.character_names.length ? shot.character_names.join(" · ") : "角色待关联"}
        </div>
        <div className="shot-state-row">
          <span className={`badge ${shot.status}`}>{statusText(shot.status)}</span>
          {shot.dirty_state !== "clean" && <span className="badge warn">需重生成</span>}
        </div>
      </div>
    </button>
  );
}

function statusText(status: string): string {
  return (
    ({ draft: "待生成", planned: "待生成", image_ready: "已生成", approved: "已确认", failed: "失败" } as Record<string, string>)[
      status
    ] ?? status
  );
}
