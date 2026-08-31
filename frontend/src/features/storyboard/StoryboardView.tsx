import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CaretDown,
  CheckCircle,
  ImageSquare,
  ListBullets,
  MagicWand,
  Plus,
  Play,
  SquaresFour,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { GenerationRead, Location, Scene, Shot, ShotSummary, Storyboard } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useOperationPolling } from "../ai/useOperationPolling";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { canonicalShotPath, useStudioRoute } from "../studio/studioRoute";
import { useNavigate, useParams } from "react-router-dom";
import { VirtualizedShotGrid } from "./VirtualizedShotGrid";
import { ShotThumbImage } from "./ShotThumbImage";
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
  const [generationMenuOpen, setGenerationMenuOpen] = useState(false);
  const [generationNotice, setGenerationNotice] = useState<string | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");

  const { data: storyboard, isLoading } = useQuery({
    queryKey: queryKeys.storyboard(sceneId),
    queryFn: () => api.get<Storyboard>(`/scenes/${sceneId}/storyboard`),
  });
  const { data: scene } = useQuery({
    queryKey: queryKeys.scene(sceneId),
    queryFn: () => api.get<Scene>(`/scenes/${sceneId}`),
    enabled: Boolean(sceneId),
  });
  // Full shot records (existing GET /scenes/{id}/shots) enrich the summary cards
  // with the real action description + camera language without changing any DTO.
  const { data: fullShots } = useQuery({
    queryKey: queryKeys.shots(sceneId),
    queryFn: () => api.get<Shot[]>(`/scenes/${sceneId}/shots`),
    enabled: Boolean(sceneId),
  });
  const { data: locations } = useQuery({
    queryKey: queryKeys.locations(projectId),
    queryFn: () => api.get<Location[]>(`/projects/${projectId}/locations`),
    enabled: Boolean(projectId) && Boolean(scene?.location_id),
  });
  const shotDetails = useMemo(() => {
    const map: Record<string, Shot> = {};
    (fullShots ?? []).forEach((shot) => {
      map[shot.id] = shot;
    });
    return map;
  }, [fullShots]);
  const sceneLocation = locations?.find((item) => item.id === scene?.location_id)?.name ?? null;

  useEffect(() => {
    if (!storyboard) return;
    if (selectedShotId && storyboard.shots.some((shot) => shot.id === selectedShotId)) return;
    // A populated demo scene opens on SH03 when available; real projects fall
    // back to the first shot without inventing production data.
    const next = storyboard.shots.find((shot) => shot.shot_number === 3) ?? storyboard.shots[0];
    if (next) selectShot(next.id);
    else clearShots();
  }, [clearShots, selectShot, selectedShotId, storyboard]);

  const createShot = useMutation({
    mutationFn: () => api.post<Shot>(`/scenes/${sceneId}/shots`, { shot_type: "medium" }),
    onSuccess: (shot) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      handleSelect(shot.id);
    },
  });

  const generateShotPlan = useMutation({
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      setPlanOpId(null);
    },
    (operation) => {
      setPlanError(new Error(operation.error ?? "AI 分镜生成失败"));
      setPlanOpId(null);
    },
  );

  const generateImages = useMutation({
    mutationFn: (targets: ShotSummary[]) =>
      Promise.all(targets.map((shot) => api.post<GenerationRead>(`/shots/${shot.id}/generations`, { type: "image" }))),
    onSuccess: (_, targets) => {
      setGenerationMenuOpen(false);
      setGenerationNotice(`已提交 ${targets.length} 个生成任务`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.generations });
    },
  });

  const handleSelect = (shotId: string) => {
    selectShot(shotId);
    setGenerationNotice(null);
  };

  const shots = storyboard?.shots ?? [];
  const currentShot = shots.find((shot) => shot.id === selectedShotId);
  const pendingShots = shots.filter(
    (shot) => !shot.active_generation && shot.status !== "image_ready" && shot.status !== "approved",
  );
  const failedShots = shots.filter((shot) => !shot.active_generation && shot.status === "failed");
  const totalDuration = shots.reduce((sum, shot) => sum + (shot.duration ?? 0), 0);
  const readyCount = shots.filter((shot) => shot.status === "image_ready" || shot.status === "approved").length;
  const sceneMeta = [scene?.time_of_day, scene?.weather, sceneLocation ?? scene?.lighting, scene?.mood].filter(
    (item): item is string => Boolean(item),
  );

  const submitImageGeneration = (targets: ShotSummary[]) => {
    if (targets.length > 0) generateImages.mutate(targets);
  };

  return (
    <div className="storyboard">
      <header className="storyboard-head scene-header">
        <div>
          <span className="scene-index mono">
            SC{String(storyboard?.scene.scene_number ?? scene?.scene_number ?? "—").padStart(2, "0")}
          </span>
          <h1>{isLoading ? "正在读取场景…" : (storyboard?.scene.name ?? scene?.name ?? "未命名场景")}</h1>
          <div className="scene-meta-line">
            {sceneMeta.length > 0 ? (
              sceneMeta.map((item) => <span key={item}>{item}</span>)
            ) : (
              <span>场景信息待补充</span>
            )}
            <span>
              {shots.length} 镜 · {totalDuration.toFixed(1)}s
            </span>
          </div>
        </div>
        <div className="scene-header-actions">
          <span className="storyboard-ready-count">
            <CheckCircle size={14} /> 已出图 {isLoading ? "…" : `${readyCount}/${shots.length}`}
          </span>
          <SceneWarningBadge sceneId={sceneId} />
          <button className="btn secondary compact" onClick={() => createShot.mutate()} disabled={createShot.isPending}>
            <Plus size={14} /> 新建镜头
          </button>
          <div className="generation-menu">
            <button
              className="btn primary compact"
              aria-haspopup="menu"
              aria-expanded={generationMenuOpen}
              disabled={generateImages.isPending || !sceneId}
              onClick={() => setGenerationMenuOpen((open) => !open)}
            >
              <Play size={13} weight="fill" /> 生成待生成镜头 <CaretDown size={13} />
            </button>
            {generationMenuOpen && (
              <div className="generation-menu-popover" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  disabled={!currentShot || generateImages.isPending}
                  onClick={() => currentShot && submitImageGeneration([currentShot])}
                >
                  生成当前镜头
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={!pendingShots.length || generateImages.isPending}
                  onClick={() => submitImageGeneration(pendingShots)}
                >
                  生成待生成镜头 <span>{pendingShots.length}</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={!failedShots.length || generateImages.isPending}
                  onClick={() => submitImageGeneration(failedShots)}
                >
                  重新生成失败镜头 <span>{failedShots.length}</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={!shots.length || generateImages.isPending}
                  onClick={() => submitImageGeneration(shots.filter((shot) => !shot.active_generation))}
                >
                  批量生成当前场景
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="storyboard-toolbar">
        <div className="continuity-score">
          <div className="continuity-track">
            <i
              style={{
                width: `${storyboard?.shots.length ? Math.max(28, Math.round((readyCount / storyboard.shots.length) * 100)) : 0}%`,
              }}
            />
          </div>
          <span>
            制作进度 {readyCount}/{shots.length}
          </span>
        </div>
        <div className="row gap">
          <button
            className="btn secondary compact"
            disabled={generateShotPlan.isPending || Boolean(planOpId)}
            onClick={() => generateShotPlan.mutate()}
          >
            <MagicWand size={15} weight="fill" />{" "}
            {generateShotPlan.isPending || planOpId ? "规划中…" : "AI 生成分镜规划"}
          </button>
          {generationNotice && <span className="generation-notice">{generationNotice}</span>}
          <div className="view-toggle" role="tablist" aria-label="Storyboard 视图">
            <button
              type="button"
              className={view === "grid" ? "active" : ""}
              aria-label="网格视图"
              title="网格视图"
              onClick={() => setView("grid")}
            >
              <SquaresFour size={16} />
            </button>
            <button
              type="button"
              className={view === "list" ? "active" : ""}
              aria-label="列表视图"
              title="列表视图"
              onClick={() => setView("list")}
            >
              <ListBullets size={16} />
            </button>
          </div>
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
            <button className="btn primary" onClick={() => generateShotPlan.mutate()}>
              <MagicWand size={16} /> AI 生成 Storyboard
            </button>
            <button className="btn secondary" onClick={() => createShot.mutate()}>
              <Plus size={16} /> 手动添加
            </button>
          </div>
        </div>
      )}

      {view === "list" ? (
        <div className="shot-list" role="list" aria-label="镜头列表">
          {storyboard?.shots.map((shot) => {
            const isSelected = selectedShotId === shot.id;
            return (
              <button
                key={shot.id}
                type="button"
                role="listitem"
                className={`shot-row ${isSelected ? "selected" : ""} ${shot.status === "failed" ? "failed" : ""}`}
                onClick={() => handleSelect(shot.id)}
              >
                <ShotThumbImage shot={shot} className="shot-row-thumb" />
                <span className="shot-row-number">Shot {String(shot.shot_number).padStart(3, "0")}</span>
                <span className="shot-row-type">{SHOT_TYPE_LABELS[shot.shot_type] ?? shot.shot_type}</span>
                <span className="shot-row-cast">
                  {shot.character_names.length ? shot.character_names.join("、") : "待编辑"}
                </span>
                <span className="shot-row-duration">
                  {shot.duration != null ? `${shot.duration.toFixed(1)}s` : "—"}
                </span>
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
          details={shotDetails}
          selectedShotId={selectedShotId}
          onSelect={handleSelect}
          onOpenShot={(shot) => {
            if (projectId && episodeId) {
              openShot({
                projectId,
                episodeId,
                shotId: shot.id,
                title: `Shot ${String(shot.shot_number).padStart(3, "0")}`,
                sceneId,
              });
              navigate(canonicalShotPath(projectId, episodeId, sceneId, shot.id));
            }
          }}
        />
      )}
    </div>
  );
}

function statusText(status: string): string {
  return (
    (
      { draft: "待生成", planned: "待生成", image_ready: "已生成", approved: "已确认", failed: "失败" } as Record<
        string,
        string
      >
    )[status] ?? status
  );
}
