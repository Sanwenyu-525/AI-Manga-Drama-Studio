import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Aperture, ArrowSquareOut, CheckCircle, Clock, DotsThree, ImageSquare, MagicWand, CaretLineRight, Trash, VideoCamera } from "@phosphor-icons/react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Character, GenerationRead, MediaVersionRead, Shot, ShotUpdatePatch } from "../../api/types";
import { SHOT_TYPES, SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

// Shot Inspector (frontend-ux §12-13): edit the selected shot, PATCH with optimistic revision.
export function ShotInspector() {
  const activeShotId = useWorkspaceStore((s) => s.activeShotId);
  const setActiveShot = useWorkspaceStore((s) => s.setActiveShot);
  const setRightPanelTab = useWorkspaceStore((s) => s.setRightPanelTab);
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
  const projectId = useSelectionStore((state) => state.selection.projectId);

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
      void queryClient.invalidateQueries({ queryKey: ["generations", activeShotId] });
    },
  });

  const deleteShot = useMutation({
    mutationFn: () => {
      if (!activeShotId) throw new Error("no active shot");
      return api.delete<{ deleted: boolean }>(`/shots/${activeShotId}`);
    },
    onSuccess: () => {
      setMenuOpen(false);
      setActiveShot(null);
      clearShots();
      if (sceneId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.shots(sceneId) });
        void queryClient.invalidateQueries({ queryKey: ["scenes"] });
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
        void queryClient.invalidateQueries({ queryKey: ["scenes"] });
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
        <PanelTabs active="inspector" onSwitch={setRightPanelTab} />
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
        <PanelTabs active="inspector" onSwitch={setRightPanelTab} />
        <p className="muted inspector-loading">正在读取镜头…</p>
      </div>
    );
  }

  return (
    <div className="panel-tab-content">
      <PanelTabs active="inspector" onSwitch={setRightPanelTab} />

      <div className="inspector">
        <div className="inspector-title-row">
          <div>
            <span className="eyebrow">SHOT DETAILS</span>
            <h2>Shot {String(shot.shot_number).padStart(3, "0")}</h2>
            <span className="ready-line"><CheckCircle size={15} weight="fill" /> {shot.status === "image_ready" ? "已出图" : "可编辑"} · rev {shot.revision}</span>
          </div>
          <div className="shot-menu" ref={menuRef}>
            <button className="icon-button" aria-label="更多操作" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}><DotsThree size={20} /></button>
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
                    if (window.confirm(`删除 Shot ${String(shot.shot_number).padStart(3, "0")}？
镜头与其生成版本将被软删除。`)) {
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

        <div className="inspector-fact-grid">
          <div><span><Aperture size={14} /> 景别</span><strong>{SHOT_TYPE_LABELS[form.shot_type ?? shot.shot_type]}</strong></div>
          <div><span><VideoCamera size={14} /> 机位</span><strong>{form.camera_angle || "未设置"}</strong></div>
          <div><span><MagicWand size={14} /> 运动</span><strong>{form.camera_movement || "静止"}</strong></div>
          <div><span><Clock size={14} /> 时长</span><strong>{form.duration ? `${form.duration}s` : "—"}</strong></div>
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
            {!characters?.length && (
              <span className="muted small">项目还没有角色 · 在左侧资源树「角色」区创建</span>
            )}
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
          <button className="btn primary grow" disabled={!dirty || saveShot.isPending} onClick={() => saveShot.mutate(form)}>
            {saveShot.isPending ? "保存中…" : dirty ? "保存修改" : "已保存"}
          </button>
          <button
            className="btn secondary"
            disabled={generate.isPending}
            onClick={() => {
              if (dirty) saveShot.mutate(form, { onSuccess: () => generate.mutate() });
              else generate.mutate();
            }}
            title="提交图片生成任务"
          >
            <MagicWand size={15} /> {generate.isPending ? "提交中…" : "生成图片"}
          </button>
        </div>
        {saveShot.isError && !conflict && <p className="error-text">保存失败：{String(saveShot.error)}</p>}
        {generate.isError && <p className="error-text">生成失败：{String(generate.error)}</p>}

        <ShotVersions shotId={shot.id} projectId={useSelectionStore.getState().selection.projectId} />
      </div>
    </div>
  );
}

function ShotVersions({ shotId, projectId }: { shotId: string; projectId?: string }) {
  const queryClient = useQueryClient();

  const { data: generations } = useQuery({
    queryKey: ["generations", shotId],
    queryFn: () => api.get<GenerationRead[]>(`/shots/${shotId}/generations`),
    refetchInterval: 2000,
  });
  const generating = (generations ?? []).some(
    (g) => g.status === "queued" || g.status === "running" || g.status === "retrying",
  );

  const { data: versions } = useQuery({
    queryKey: ["versions", shotId],
    queryFn: () => api.get<MediaVersionRead[]>(`/shots/${shotId}/versions`),
    refetchInterval: generating ? 800 : 3000, // poll faster while a generation runs
  });

  const activate = useMutation({
    mutationFn: (versionId: string) => api.post<MediaVersionRead>(`/media-versions/${versionId}/activate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["versions", shotId] });
      void queryClient.invalidateQueries({ queryKey: ["storyboard"] });
    },
  });

  if (!versions || versions.length === 0) {
    return (
      <div className="versions-block">
        <h4>版本</h4>
        <p className="muted small">还没有生成结果。点击「生成图片」创建 V1。</p>
      </div>
    );
  }

  const active = versions.find((v) => v.is_active);
  return (
    <div className="versions-block">
      <div className="versions-title-row">
        <h4>版本（{versions.length}）</h4>
        {projectId && <Link className="text-action" to={`/projects/${projectId}/shots/${shotId}/versions`}>全屏审片 <ArrowSquareOut size={14} /></Link>}
      </div>
      {active && (
        <img
          className="version-preview"
          src={`/api/v1/assets/${active.asset_id}/content`}
          alt={`V${active.version_number}`}
        />
      )}
      <div className="version-row-list">
        {versions.map((v) => (
          <div key={v.id} className={`version-row ${v.is_active ? "active" : ""}`}>
            <img
              className="version-thumb"
              src={`/api/v1/assets/${v.asset_id}/thumbnail`}
              alt={`V${v.version_number}`}
            />
            <span className="version-label">V{v.version_number}</span>
            {v.is_active ? (
              <span className="badge ok">Active</span>
            ) : (
              <button className="btn tiny" onClick={() => activate.mutate(v.id)} disabled={activate.isPending}>
                设为当前
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PanelTabs({ active, onSwitch }: { active: "inspector" | "director"; onSwitch: (tab: "inspector" | "director") => void }) {
  const setRightPanelCollapsed = useWorkspaceStore((state) => state.setRightPanelCollapsed);
  return (
    <div className="panel-tabs">
      <button className={`tab ${active === "inspector" ? "active" : ""}`} onClick={() => onSwitch("inspector")}>
        镜头检查器
      </button>
      <button className={`tab ${active === "director" ? "active" : ""}`} onClick={() => onSwitch("director")}>
        AI Director
      </button>
      <button type="button" className="tab panel-collapse-tab" title="收起右侧面板" aria-label="收起右侧面板" onClick={() => setRightPanelCollapsed(true)}>
        <CaretLineRight size={15} />
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
