import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CaretDown,
  CheckCircle,
  ImageSquare,
  ListBullets,
  MagicWand,
  MapPin,
  Plus,
  Play,
  SquaresFour,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { Location, Scene, Shot, ShotSummary, Storyboard } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useOperationPolling } from "../ai/useOperationPolling";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { canonicalShotPath, useStudioRoute } from "../studio/studioRoute";
import { useNavigate, useParams } from "react-router-dom";
import { VirtualizedShotGrid, type ShotSelectMods } from "./VirtualizedShotGrid";
import { ShotThumbImage } from "./ShotThumbImage";
import { SceneWarningBadge } from "../continuity/SceneWarningBadge";
import { BatchActionBar } from "./BatchActionBar";
import { generationBatchNotice, submitImageGenerations } from "../generation/batchSubmit";

export function StoryboardView({ sceneId }: { sceneId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { episodeId = "" } = useParams();
  const shotIds = useSelectionStore((state) => state.selection.shotIds);
  const selectedShotId = shotIds[0];
  const selectShot = useSelectionStore((state) => state.selectShot);
  const toggleShot = useSelectionStore((state) => state.toggleShot);
  const setShotIds = useSelectionStore((state) => state.setShotIds);
  const clearShots = useSelectionStore((state) => state.clearShots);
  const openShot = useEditorTabsStore((state) => state.openShot);
  const projectId = useStudioRoute().projectId;
  const [planOpId, setPlanOpId] = useState<string | null>(null);
  const [planError, setPlanError] = useState<Error | null>(null);
  const [generationMenuOpen, setGenerationMenuOpen] = useState(false);
  const [generationNotice, setGenerationNotice] = useState<string | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [selectAnchorId, setSelectAnchorId] = useState<string | null>(null);

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
    enabled: Boolean(projectId),
  });
  const shotDetails = useMemo(() => {
    const map: Record<string, Shot> = {};
    (fullShots ?? []).forEach((shot) => {
      map[shot.id] = shot;
    });
    return map;
  }, [fullShots]);
  const sceneLocation = locations?.find((item) => item.id === scene?.location_id)?.name ?? null;
  // 自主迭代 03：场景 ↔ 地点绑定（生成时注入地点 MASTER 参考图 → 场景一致性）。
  const [locationMenuOpen, setLocationMenuOpen] = useState(false);
  const bindLocation = useMutation({
    mutationFn: (locationId: string | null) =>
      api.patch<Scene>(`/scenes/${sceneId}`, {
        revision: scene?.revision ?? 0,
        patch: { location_id: locationId },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scene(sceneId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.generations }); // 参考图预览随绑定变化
      setLocationMenuOpen(false);
    },
  });

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
    mutationFn: (targets: ShotSummary[]) => submitImageGenerations(targets),
    onSuccess: (summary) => {
      setGenerationMenuOpen(false);
      setGenerationNotice(generationBatchNotice(summary));
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.generations });
    },
  });

  const handleSelect = (shotId: string, mods?: ShotSelectMods) => {
    if (mods?.toggle) {
      toggleShot(shotId);
      setSelectAnchorId(shotId);
      return;
    }
    if (mods?.shift && selectAnchorId) {
      const orderedIds = (storyboard?.shots ?? []).map((shot) => shot.id);
      const from = orderedIds.indexOf(selectAnchorId);
      const to = orderedIds.indexOf(shotId);
      if (from !== -1 && to !== -1) {
        const [start, end] = from <= to ? [from, to] : [to, from];
        setShotIds(orderedIds.slice(start, end + 1));
        return;
      }
    }
    setSelectAnchorId(shotId);
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
          <div className="generation-menu location-menu">
            <button
              type="button"
              className={`btn secondary compact ${sceneLocation ? "has-location" : ""}`}
              aria-haspopup="menu"
              aria-expanded={locationMenuOpen}
              title="绑定场景地点（生成时注入地点参考图，保证环境稳定）"
              onClick={() => setLocationMenuOpen((open) => !open)}
            >
              <MapPin size={13} weight="fill" /> {sceneLocation ?? "绑定地点"} <CaretDown size={11} />
            </button>
            {locationMenuOpen && (
              <div className="generation-menu-popover" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  disabled={scene?.location_id == null}
                  onClick={() => bindLocation.mutate(null)}
                >
                  不绑定
                </button>
                {(locations ?? []).map((loc) => (
                  <button
                    type="button"
                    role="menuitem"
                    key={loc.id}
                    disabled={loc.id === scene?.location_id}
                    onClick={() => bindLocation.mutate(loc.id)}
                  >
                    {loc.name}
                    {loc.master_version_id ? " · MASTER" : " · 无参考图"}
                  </button>
                ))}
                {!locations?.length && (
                  <span className="muted small generation-menu-empty">
                    还没有地点 — 在活动栏「地点」创建并上传参考图。
                  </span>
                )}
              </div>
            )}
          </div>
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

      {shotIds.length > 1 && !isLoading && storyboard && storyboard.shots.length > 0 && (
        <BatchActionBar sceneId={sceneId} shots={storyboard.shots} selectedIds={shotIds} onNotice={setGenerationNotice} />
      )}

      {planError && <ApiErrorPanel error={planError} />}
      {(generateImages.error || createShot.error) && (
        <ApiErrorPanel error={generateImages.error ?? createShot.error} />
      )}
      {isLoading && <div className="workspace-loading">正在读取 Storyboard…</div>}

      {!isLoading && (!storyboard || storyboard.shots.length === 0) && (
        <div className="empty-state storyboard-empty">
          <ImageSquare size={38} />
          <h2>这一场还没有镜头</h2>
          <p>让 AI 根据场景生成镜头计划，或先手动添加一个镜头。</p>
          <div className="row gap">
            <button
              className="btn primary"
              disabled={generateShotPlan.isPending || Boolean(planOpId)}
              onClick={() => generateShotPlan.mutate()}
            >
              <MagicWand size={16} /> {generateShotPlan.isPending || planOpId ? "规划中…" : "AI 生成 Storyboard"}
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
                onClick={(event) =>
                  handleSelect(shot.id, {
                    toggle: event.ctrlKey || event.metaKey,
                    shift: event.shiftKey,
                  })
                }
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
          multiSelectedIds={shotIds}
          onToggleSelect={toggleShot}
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
