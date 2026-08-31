import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Aperture,
  ArrowSquareOut,
  CheckCircle,
  Clock,
  DotsThree,
  ImageSquare,
  MagicWand,
  Trash,
  VideoCamera,
} from "@phosphor-icons/react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type {
  AssetVersionRead,
  Character,
  ContinuityShotReadCard,
  GenerationRead,
  Scene,
  Shot,
  ShotUpdatePatch,
} from "../../api/types";
import { SHOT_TYPES, SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { VersionStrip } from "../versioning/VersionStrip";
import { ShotContinuityCard } from "../continuity/ShotContinuityCard";
import { canonicalStoryboardPath, useStudioRoute } from "../studio/studioRoute";

// Shot Inspector (frontend-ux §12-13): edit the selected shot, PATCH with optimistic revision.
// Lives only in the right Agent Dock (P6 职责边界) — the center canvas shows the storyboard.
export function ShotInspector() {
  const route = useStudioRoute();
  const selectedShotId = useSelectionStore((s) => s.selection.shotIds[0]);
  const activeShotId = route.shotId ?? selectedShotId;
  const clearShots = useSelectionStore((s) => s.clearShots);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const { data: shot, isLoading } = useQuery({
    queryKey: activeShotId ? queryKeys.shot(activeShotId) : ["shot", "none"],
    queryFn: () => api.get<Shot>(`/shots/${activeShotId}`),
    enabled: !!activeShotId,
  });

  const [form, setForm] = useState<Partial<ShotUpdatePatch>>({});
  const [conflict, setConflict] = useState<string | null>(null);

  useEffect(() => {
    if (shot) {
      setForm({
        shot_type: shot.shot_type,
        camera_angle: shot.camera_angle ?? "",
        camera_movement: shot.camera_movement ?? "",
        duration: shot.duration ?? undefined,
        action: shot.action ?? "",
        emotion: shot.emotion ?? "",
        dialogue: shot.dialogue ?? "",
        image_prompt: shot.image_prompt ?? "",
        character_ids: shot.character_ids ?? [],
      });
      setConflict(null);
    }
  }, [shot]);

  const sceneId = shot?.scene_id;
  const projectId = route.projectId;

  const { data: characters } = useQuery({
    queryKey: projectId ? queryKeys.characters(projectId) : ["characters", "none"],
    queryFn: () => api.get<Character[]>(`/projects/${projectId}/characters`),
    enabled: !!projectId,
  });

  const toggleCharacter = (id: string) => {
    setForm((f) => {
      const current = f.character_ids ?? shot?.character_ids ?? [];
      const next = current.includes(id) ? current.filter((c) => c !== id) : [...current, id];
      return { ...f, character_ids: next };
    });
  };

  const generate = useMutation({
    mutationFn: () => {
      if (!activeShotId) throw new Error("no active shot");
      return api.post<GenerationRead>(`/shots/${activeShotId}/generations`, { type: "image" });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.shotGenerations(activeShotId) });
    },
  });

  // Agnes 接入：镜头视频生成（文生视频，prompt 取镜头动作描述）。
  const videoPrompt = (form.action ?? "").trim();
  const generateVideo = useMutation({
    mutationFn: () => {
      if (!activeShotId) throw new Error("no active shot");
      return api.post<GenerationRead>(`/shots/${activeShotId}/generations`, {
        type: "video",
        prompt: videoPrompt || undefined,
        seconds: 5,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.shotGenerations(activeShotId) });
    },
  });

  const deleteShot = useMutation({
    mutationFn: () => {
      if (!activeShotId) throw new Error("no active shot");
      return api.delete<{ deleted: boolean }>(`/shots/${activeShotId}`);
    },
    onSuccess: () => {
      setMenuOpen(false);
      clearShots();
      if (sceneId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.shots(sceneId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
        if (route.episodeId && route.workspace === "shot") {
          navigate(canonicalStoryboardPath(projectId, route.episodeId, route.sceneId ?? sceneId));
        }
      }
    },
    onError: (error) => setConflict(error instanceof Error ? error.message : String(error)),
  });

  const saveShot = useMutation({
    mutationFn: (patch: Partial<ShotUpdatePatch>) => {
      if (!activeShotId || !shot) throw new Error("no active shot");
      // character_ids is list-replace semantics on the backend: only send it when
      // the user actually changed the cast, so unrelated saves don't bump revision.
      const body: Partial<ShotUpdatePatch> = { ...patch };
      if (JSON.stringify(patch.character_ids ?? []) === JSON.stringify(shot.character_ids ?? [])) {
        delete body.character_ids;
      }
      return api.patch<Shot>(`/shots/${activeShotId}`, { revision: shot.revision, patch: body });
    },
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.shot(activeShotId!) });
      if (sceneId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.shots(sceneId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      }
      setForm((f) => ({ ...f, ...updated }));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "CONFLICT") {
        setConflict("该镜头已被其他修改更新（revision 冲突），请刷新后重试。");
        void queryClient.invalidateQueries({ queryKey: queryKeys.shot(activeShotId!) });
      } else {
        setConflict(error instanceof Error ? error.message : String(error));
      }
    },
  });

  const dirty = useMemo(() => {
    if (!shot) return false;
    return (
      (form.shot_type ?? "") !== shot.shot_type ||
      (form.camera_angle ?? "") !== (shot.camera_angle ?? "") ||
      (form.camera_movement ?? "") !== (shot.camera_movement ?? "") ||
      (form.duration ?? undefined) !== (shot.duration ?? undefined) ||
      (form.action ?? "") !== (shot.action ?? "") ||
      (form.emotion ?? "") !== (shot.emotion ?? "") ||
      (form.dialogue ?? "") !== (shot.dialogue ?? "") ||
      (form.image_prompt ?? "") !== (shot.image_prompt ?? "") ||
      JSON.stringify(form.character_ids ?? []) !== JSON.stringify(shot.character_ids ?? [])
    );
  }, [form, shot]);

  if (!activeShotId) {
    return (
      <div className="panel-tab-content">
        <div className="placeholder-note inspector-empty">
          <ImageSquare size={32} />
          <h3>选择一个镜头</h3>
          <p>在 Storyboard 里选择 Shot，参数和版本会显示在这里。</p>
        </div>
      </div>
    );
  }

  if (isLoading || !shot) {
    return (
      <div className="panel-tab-content">
        <p className="muted inspector-loading">正在读取镜头…</p>
      </div>
    );
  }

  return (
    <div className="panel-tab-content">
      <div className="inspector">
        <div className="inspector-title-row">
          <div>
            <span className="eyebrow">镜头检查器</span>
            <h2>Shot {String(shot.shot_number).padStart(3, "0")}</h2>
            <span className="ready-line">
              <CheckCircle size={15} weight="fill" /> {shot.status === "image_ready" ? "已出图" : "可编辑"} · rev{" "}
              {shot.revision}
            </span>
          </div>
          <div className="shot-menu" ref={menuRef}>
            <button
              className="icon-button"
              aria-label="更多操作"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            >
              <DotsThree size={20} />
            </button>
            {menuOpen && (
              <div className="shot-menu-popover" role="menu" aria-label="镜头操作">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    navigate(`/projects/${projectId}/shots/${activeShotId}/versions`);
                  }}
                >
                  <ArrowSquareOut size={15} /> 全屏审片
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="danger"
                  disabled={deleteShot.isPending}
                  onClick={() => {
                    setMenuOpen(false);
                    if (
                      window.confirm(`删除 Shot ${String(shot.shot_number).padStart(3, "0")}？
镜头与其生成版本将被软删除。`)
                    ) {
                      deleteShot.mutate();
                    }
                  }}
                >
                  <Trash size={15} /> {deleteShot.isPending ? "删除中…" : "删除镜头"}
                </button>
              </div>
            )}
          </div>
        </div>

        <InspectorChecks shot={shot} />

        <div className="inspector-fact-grid">
          <div>
            <span>
              <Aperture size={14} /> 景别
            </span>
            <strong>{SHOT_TYPE_LABELS[form.shot_type ?? shot.shot_type]}</strong>
          </div>
          <div>
            <span>
              <VideoCamera size={14} /> 机位
            </span>
            <strong>{form.camera_angle || "未设置"}</strong>
          </div>
          <div>
            <span>
              <MagicWand size={14} /> 运动
            </span>
            <strong>{form.camera_movement || "静止"}</strong>
          </div>
          <div>
            <span>
              <Clock size={14} /> 时长
            </span>
            <strong>{form.duration ? `${form.duration}s` : "—"}</strong>
          </div>
        </div>

        <div className="inspector-section-title">镜头参数</div>

        <Field label="景别">
          <select
            value={form.shot_type ?? shot.shot_type}
            onChange={(e) => setForm((f) => ({ ...f, shot_type: e.target.value }))}
          >
            {SHOT_TYPES.map((t) => (
              <option key={t} value={t}>
                {SHOT_TYPE_LABELS[t]} ({t})
              </option>
            ))}
          </select>
        </Field>

        <Field label="机位角度">
          <input
            value={form.camera_angle ?? ""}
            placeholder="low_angle / high_angle / eye_level"
            onChange={(e) => setForm((f) => ({ ...f, camera_angle: e.target.value }))}
          />
        </Field>

        <Field label="镜头运动">
          <input
            value={form.camera_movement ?? ""}
            placeholder="static / pan / dolly / handheld"
            onChange={(e) => setForm((f) => ({ ...f, camera_movement: e.target.value }))}
          />
        </Field>

        <Field label="时长 (秒)">
          <input
            type="number"
            step="0.1"
            min="0.1"
            value={form.duration ?? ""}
            placeholder="3.0"
            onChange={(e) => setForm((f) => ({ ...f, duration: e.target.value ? Number(e.target.value) : undefined }))}
          />
        </Field>

        <Field label="动作">
          <input value={form.action ?? ""} onChange={(e) => setForm((f) => ({ ...f, action: e.target.value }))} />
        </Field>

        <Field label="情绪">
          <input value={form.emotion ?? ""} onChange={(e) => setForm((f) => ({ ...f, emotion: e.target.value }))} />
        </Field>

        <Field label="对白">
          <textarea
            rows={2}
            value={form.dialogue ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, dialogue: e.target.value }))}
          />
        </Field>

        <Field label="出场角色">
          <div className="char-picker">
            {(characters ?? []).map((c) => (
              <label key={c.id} className="char-chip">
                <input
                  type="checkbox"
                  checked={(form.character_ids ?? shot.character_ids ?? []).includes(c.id)}
                  onChange={() => toggleCharacter(c.id)}
                />
                {c.name}
              </label>
            ))}
            {!characters?.length && <span className="muted small">项目还没有角色 · 在活动栏「角色」页创建</span>}
          </div>
        </Field>

        <Field label="Image Prompt">
          <textarea
            rows={4}
            value={form.image_prompt ?? ""}
            placeholder="该镜头的图片生成提示词（Stage C 生效）"
            onChange={(e) => setForm((f) => ({ ...f, image_prompt: e.target.value }))}
          />
        </Field>

        {conflict && <p className="error-text">{conflict}</p>}

        <div className="inspector-actions">
          <button
            className="btn primary grow"
            disabled={!dirty || saveShot.isPending}
            onClick={() => saveShot.mutate(form)}
          >
            {saveShot.isPending ? "保存中…" : dirty ? "保存修改" : "已保存"}
          </button>
          <button
            className="btn secondary"
            disabled={generate.isPending}
            onClick={() => {
              if (dirty) saveShot.mutate(form, { onSuccess: () => generate.mutate() });
              else generate.mutate();
            }}
            title="提交当前镜头的图片生成任务"
          >
            <MagicWand size={15} /> {generate.isPending ? "提交中…" : "生成当前镜头"}
          </button>
        </div>
        <button
          className="btn secondary grow"
          disabled={generateVideo.isPending || !videoPrompt}
          onClick={() => {
            if (dirty) saveShot.mutate(form, { onSuccess: () => generateVideo.mutate() });
            else generateVideo.mutate();
          }}
          title={
            videoPrompt
              ? "提交当前镜头的视频生成任务（Agnes 文生视频，约 1–2 分钟）"
              : "需要动作/画面描述作为视频提示词"
          }
        >
          <VideoCamera size={14} /> {generateVideo.isPending ? "视频提交中…" : "生成视频"}
        </button>
        {generateVideo.isError && <p className="error-text">视频生成失败：{String(generateVideo.error)}</p>}
        {saveShot.isError && !conflict && <p className="error-text">保存失败：{String(saveShot.error)}</p>}
        {generate.isError && <p className="error-text">生成失败：{String(generate.error)}</p>}

        <ShotVersions shotId={shot.id} projectId={projectId} />

        <ShotContinuityCard shotId={shot.id} />
      </div>
    </div>
  );
}

// Compact pre-flight check strip (frontend-ux §15): continuity/character/scene/
// framing are derived from real API state; prompt completeness counts the fields
// that feed the image generation prompt. No fabricated values.
function InspectorChecks({ shot }: { shot: Shot }) {
  const { data: continuity } = useQuery({
    queryKey: queryKeys.shotContinuity(shot.id),
    queryFn: () => api.get<ContinuityShotReadCard>(`/shots/${shot.id}/continuity-state`),
  });
  const { data: scene } = useQuery({
    queryKey: queryKeys.scene(shot.scene_id),
    queryFn: () => api.get<Scene>(`/scenes/${shot.scene_id}`),
  });

  const warningCount = continuity?.warnings?.length ?? 0;
  const sceneOk = Boolean(scene && (scene.time_of_day || scene.location_id || scene.mood || scene.lighting));
  const framingOk = Boolean(shot.camera_angle && shot.camera_movement);
  const promptFields = [
    shot.image_prompt,
    shot.action,
    shot.camera_angle,
    shot.camera_movement,
    shot.duration,
    shot.emotion,
  ];
  const promptScore = Math.round(
    (promptFields.filter((f) => f !== null && f !== undefined && f !== "").length / promptFields.length) * 100,
  );

  const rows: Array<{ label: string; ok: boolean; note: string }> = [
    { label: "连续性", ok: warningCount === 0, note: warningCount === 0 ? "无警告" : `${warningCount} 个警告` },
    {
      label: "角色一致性",
      ok: shot.character_ids.length > 0,
      note: shot.character_ids.length > 0 ? "已关联参考" : "未关联角色",
    },
    { label: "场景一致性", ok: sceneOk, note: sceneOk ? "已对齐" : "待补充场景信息" },
    { label: "构图检查", ok: framingOk, note: framingOk ? "机位与运动完整" : "1 个建议" },
  ];

  return (
    <div className="inspector-checks">
      {rows.map((row) => (
        <div key={row.label} className={`inspector-check ${row.ok ? "ok" : "warn"}`}>
          <span className="inspector-check-label">{row.label}</span>
          <strong>{row.ok ? "✓" : "!"}</strong>
          <span className="inspector-check-note">{row.note}</span>
        </div>
      ))}
      <div className={`inspector-check ${promptScore >= 80 ? "ok" : "warn"}`}>
        <span className="inspector-check-label">Prompt 完整度</span>
        <strong>{promptScore}%</strong>
        <span className="inspector-check-note">{promptScore >= 80 ? "可生成" : "建议补全"}</span>
      </div>
    </div>
  );
}

function ShotVersions({ shotId, projectId }: { shotId: string; projectId?: string }) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: generations } = useQuery({
    queryKey: queryKeys.shotGenerations(shotId),
    queryFn: () => api.get<GenerationRead[]>(`/shots/${shotId}/generations`),
    refetchInterval: 2000,
  });
  const generating = (generations ?? []).some(
    (g) => g.status === "queued" || g.status === "running" || g.status === "retrying",
  );

  const { data: versions } = useQuery({
    queryKey: queryKeys.shotVersions(shotId),
    queryFn: () => api.get<AssetVersionRead[]>(`/shots/${shotId}/versions`),
    refetchInterval: generating ? 800 : 3000, // poll faster while a generation runs
  });

  // Keep selection in sync with the active version while versions refresh (no explicit pick).
  useEffect(() => {
    if (!versions || versions.length === 0) return;
    const active = versions.find((v) => v.is_active);
    setSelectedId((cur) =>
      cur && versions.some((v) => v.asset_id === cur) ? cur : (active?.asset_id ?? versions[0].asset_id),
    );
  }, [versions]);

  const activate = useMutation({
    mutationFn: (assetId: string) => api.post<AssetVersionRead>(`/media-versions/${assetId}/activate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.shotVersions(shotId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard });
    },
  });

  if (!versions || versions.length === 0) {
    return (
      <div className="versions-block">
        <h4>版本</h4>
        <p className="muted small">还没有生成结果。点击「生成当前镜头」创建 V1。</p>
      </div>
    );
  }

  const active = versions.find((v) => v.is_active);
  const selected = versions.find((v) => v.asset_id === selectedId) ?? active;
  const selectedIsActive = !!selected?.is_active;
  return (
    <div className="versions-block">
      <div className="versions-title-row">
        <h4>版本（{versions.length}）</h4>
        {projectId && (
          <Link className="text-action" to={`/projects/${projectId}/shots/${shotId}/versions`}>
            全屏审片 <ArrowSquareOut size={14} />
          </Link>
        )}
      </div>
      {active &&
        (active.media_type === "video" ? (
          <video className="version-preview" src={`/api/v1/assets/${active.asset_id}/content`} controls muted loop />
        ) : (
          <img
            className="version-preview"
            src={`/api/v1/assets/${active.asset_id}/content`}
            alt={`V${active.version_number}`}
          />
        ))}
      <VersionStrip versions={versions} selectedId={selectedId} onSelect={setSelectedId} title="版本条" />
      <button
        className="btn tiny"
        disabled={!selected || selectedIsActive || activate.isPending}
        onClick={() => selected && activate.mutate(selected.asset_id)}
        title="把选中的版本切换为当前生效版本"
      >
        {selectedIsActive ? "当前生效" : activate.isPending ? "切换中…" : "设为当前版本"}
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}
