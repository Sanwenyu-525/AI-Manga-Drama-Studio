import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, ImageSquare, ListBullets, MagicWand, Plus, SquaresFour } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { Shot, Storyboard } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useOperationPolling } from "../ai/useOperationPolling";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { canonicalShotPath, useStudioRoute } from "../studio/studioRoute";
import { useNavigate, useParams } from "react-router-dom";
import { VirtualizedShotGrid } from "./VirtualizedShotGrid";
import { SceneWarningBadge } from "../continuity/SceneWarningBadge";

export function StoryboardView({ sceneId }: { sceneId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { episodeId = "" } = useParams();
  const selectedShotId = useSelectionStore((state) => state.selection.shotIds[0]);
  const selectShot = useSelectionStore((state) => state.selectShot);
  const clearShots = useSelectionStore((state) => state.clearShots);
  const openShot = useEditorTabsStore((state) => state.openShot);
  const projectId = useStudioRoute().projectId;
  const [planOpId, setPlanOpId] = useState<string | null>(null);
  const [planError, setPlanError] = useState<Error | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");

  const { data: storyboard, isLoading } = useQuery({
    queryKey: queryKeys.storyboard(sceneId),
    queryFn: () => api.get<Storyboard>(`/scenes/${sceneId}/storyboard`),
  });

  useEffect(() => {
    if (selectedShotId && storyboard && !storyboard.shots.some((shot) => shot.id === selectedShotId)) clearShots();
  }, [clearShots, selectedShotId, storyboard]);

  const createShot = useMutation({
    mutationFn: () => api.post<Shot>(`/scenes/${sceneId}/shots`, { shot_type: "medium" }),
    onSuccess: (shot) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
      handleSelect(shot.id);
    },
  });

  const generateShots = useMutation({
    mutationFn: () => api.post<{ operation_id: string; status: string }>(`/scenes/${sceneId}/generate-shots`),
    onSuccess: (response) => {
      setPlanOpId(response.operation_id);
      setPlanError(null);
    },
    onError: (error) => setPlanError(error instanceof Error ? error : new Error(String(error))),
  });

  useOperationPolling(
    planOpId,
    () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
      setPlanOpId(null);
    },
    (operation) => {
      setPlanError(new Error(operation.error ?? "AI 分镜生成失败"));
      setPlanOpId(null);
    },
  );

  const handleSelect = (shotId: string) => {
    selectShot(shotId);
  };

  const totalDuration = storyboard?.shots.reduce((sum, shot) => sum + (shot.duration ?? 0), 0) ?? 0;
  const readyCount = storyboard?.shots.filter((shot) => shot.status === "image_ready" || shot.status === "approved").length ?? 0;

  return (
    <div className="storyboard">
      <header className="storyboard-head">
        <div>
          <span className="eyebrow">STORYBOARD</span>
          <h1>第 {storyboard?.scene.scene_number ?? "—"} 场 · {storyboard?.scene.name ?? "分镜"}</h1>
          <p>{storyboard?.shots.length ?? 0} 个镜头 · {totalDuration.toFixed(1)}s</p>
        </div>
        <div className="storyboard-summary">
          <span><CheckCircle size={16} /> 已出图 {readyCount}/{storyboard?.shots.length ?? 0}</span>
          <SceneWarningBadge sceneId={sceneId} />
          <div className="view-toggle" role="tablist" aria-label="Storyboard 视图">
            <button type="button" className={view === "grid" ? "active" : ""} aria-label="网格视图" title="网格视图" onClick={() => setView("grid")}><SquaresFour size={17} /></button>
            <button type="button" className={view === "list" ? "active" : ""} aria-label="列表视图" title="列表视图" onClick={() => setView("list")}><ListBullets size={17} /></button>
          </div>
        </div>
      </header>

      <div className="storyboard-toolbar">
        <div className="continuity-score"><div className="continuity-track"><i style={{ width: `${storyboard?.shots.length ? Math.max(28, Math.round((readyCount / storyboard.shots.length) * 100)) : 0}%` }} /></div><span>制作进度</span></div>
        <div className="row gap">
          <button className="btn secondary" onClick={() => createShot.mutate()} disabled={createShot.isPending}><Plus size={15} /> 镜头</button>
          <button className="btn primary" disabled={generateShots.isPending || Boolean(planOpId)} onClick={() => generateShots.mutate()}>
            <MagicWand size={16} weight="fill" /> {generateShots.isPending || planOpId ? "AI 生成中…" : "AI 生成分镜"}
          </button>
        </div>
      </div>

      {planError && <ApiErrorPanel error={planError} />}
      {isLoading && <div className="workspace-loading">正在读取 Storyboard…</div>}

      {!isLoading && (!storyboard || storyboard.shots.length === 0) && (
        <div className="empty-state storyboard-empty">
          <ImageSquare size={38} />
          <h2>这一场还没有镜头</h2>
          <p>让 AI 根据场景生成镜头计划，或先手动添加一个镜头。</p>
          <div className="row gap">
            <button className="btn primary" onClick={() => generateShots.mutate()}><MagicWand size={16} /> AI 生成 Storyboard</button>
            <button className="btn secondary" onClick={() => createShot.mutate()}><Plus size={16} /> 手动添加</button>
          </div>
        </div>
      )}

      {view === "list" ? (
        <div className="shot-list" role="list" aria-label="镜头列表">
          {storyboard?.shots.map((shot) => {
            const isSelected = selectedShotId === shot.id;
            return (
              <button key={shot.id} type="button" role="listitem" className={`shot-row ${isSelected ? "selected" : ""} ${shot.status === "failed" ? "failed" : ""}`} onClick={() => handleSelect(shot.id)}>
                <img className="shot-row-thumb" loading="lazy" src={shot.thumbnail_url ?? "/assets/manga-shot.png"} alt={`Shot ${shot.shot_number}`} />
                <span className="shot-row-number">Shot {String(shot.shot_number).padStart(3, "0")}</span>
                <span className="shot-row-type">{SHOT_TYPE_LABELS[shot.shot_type] ?? shot.shot_type}</span>
                <span className="shot-row-cast">{shot.character_names.length ? shot.character_names.join("、") : "待编辑"}</span>
                <span className="shot-row-duration">{shot.duration != null ? `${shot.duration.toFixed(1)}s` : "—"}</span>
                <span className="shot-row-state">
                  <span className={`badge ${shot.status}`}>{statusText(shot.status)}</span>
                  {shot.dirty_state !== "clean" && <span className="badge warn">需重生成</span>}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <VirtualizedShotGrid
          shots={storyboard?.shots ?? []}
          selectedShotId={selectedShotId}
          onSelect={handleSelect}
          onOpenShot={(shot) => {
            if (projectId && episodeId) {
              openShot({ projectId, episodeId, shotId: shot.id, title: `Shot ${String(shot.shot_number).padStart(3, "0")}`, sceneId });
              navigate(canonicalShotPath(projectId, episodeId, sceneId, shot.id));
            }
          }}
        />
      )}
    </div>
  );
}

function statusText(status: string): string {
  return ({ draft: "草稿", image_ready: "已出图", approved: "已确认", failed: "失败" } as Record<string, string>)[status] ?? status;
}
