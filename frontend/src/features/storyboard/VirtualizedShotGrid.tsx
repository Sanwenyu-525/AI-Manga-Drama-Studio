// P6-T008 Virtualized Shot Grid — windowed card rendering for the Storyboard.
// Small scenes (<= pageSize shots, incl. the existing 20-shot case) render exactly
// as before — full grid, no virtualization. Large scenes mount only a bounded
// [startIndex, endIndex) window so per-card markup stays identical and layout
// stays stable while scrolling.

import { MagicWand } from "@phosphor-icons/react";
import type { ShotSummary } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { useVirtualizedGrid } from "./useVirtualizedGrid";

interface VirtualizedShotGridProps {
  shots: ShotSummary[];
  selectedShotId?: string;
  onSelect: (shotId: string) => void;
  /** Open the shot in a center Editor Tab (double-click). */
  onOpenShot?: (shot: ShotSummary) => void;
  /** Threshold below which we render everything (no virtualization). */
  pageSize?: number;
}

export function VirtualizedShotGrid({ shots, selectedShotId, onSelect, onOpenShot, pageSize = 60 }: VirtualizedShotGridProps) {
  const small = shots.length <= pageSize;
  const virtual = useVirtualizedGrid(shots.length, { pageSize });
  const { startIndex, endIndex, gridRef } = virtual;

  if (small || endIndex <= startIndex) {
    return (
      <div className="shot-grid shot-grid--plain">
        {shots.map((shot, i) => renderCard(shot, selectedShotId, onSelect, onOpenShot, i))}
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
        {visible.map((shot, i) => renderCard(shot, selectedShotId, onSelect, onOpenShot, startIndex + i))}
      </div>
      {endIndex < shots.length && (<div className="shot-grid-sentinel" data-testid="shot-grid-sentinel">已加载 {endIndex}/{shots.length} 个镜头 · 滚动加载更多</div>)}
    </div>
  );
}

function renderCard(shot: ShotSummary, selectedShotId: string | undefined, onSelect: (id: string) => void, onOpenShot: ((shot: ShotSummary) => void) | undefined, key: number) {
  const isSelected = selectedShotId === shot.id;
  const isGenerating = shot.active_generation && typeof shot.active_generation === "object";
  return (
    <button key={key} type="button" className={`shot-card ${isSelected ? "selected" : ""} ${shot.status === "failed" ? "failed" : ""}`} onClick={() => onSelect(shot.id)} onDoubleClick={() => onOpenShot?.(shot)}>
      <div className="shot-thumb">
        <img
          loading="lazy"
          src={shot.thumbnail_url ?? "/assets/manga-shot.png"}
          alt={"Shot " + shot.shot_number}
          className={shot.thumbnail_url ? undefined : "reference-fallback"}
        />
        {isGenerating && <div className="shot-generating"><MagicWand size={18} /> GENERATING</div>}
        <span className="shot-index">SH{String(shot.shot_number).padStart(2, "0")}</span>
      </div>
      <div className="shot-card-body">
        <div className="shot-meta">
          <span className="shot-number">Shot {String(shot.shot_number).padStart(3, "0")}</span>
          <span className="shot-duration">{shot.duration != null ? `${shot.duration.toFixed(1)}s` : "—"}</span>
        </div>
        <p>{SHOT_TYPE_LABELS[shot.shot_type] ?? shot.shot_type}{shot.character_names.length ? ` · ${shot.character_names.join("、")}` : " · 待编辑"}</p>
        <div className="shot-state-row">
          <span className={`badge ${shot.status}`}>{statusText(shot.status)}</span>
          {shot.dirty_state !== "clean" && <span className="badge warn">需重生成</span>}
        </div>
      </div>
    </button>
  );
}

function statusText(status: string): string {
  return ({ draft: "草稿", image_ready: "已出图", approved: "已确认", failed: "失败" } as Record<string, string>)[status] ?? status;
}