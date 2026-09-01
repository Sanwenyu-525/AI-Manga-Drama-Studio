// 自主迭代 06 — 场景信息编辑（Scene Properties）：让 AI 拆解后的场景环境可人工细化。
//
// 编辑时段/光照/天气/氛围/描述 → PATCH /scenes/{id}。后端零改动：SceneUpdate 支持全部
// 字段，且 update_scene 内置 P8-T017 hook——场景基准变更 → 连续性重算 + 活跃资产 stale
// 标记（不自动重生成，引导用户重生成受影响镜头）。空字符串 = 清空该字段。
//
// 复用优先：api.patch + ApiErrorPanel + queryKeys；409 乐观并发冲突 → 提示关闭重开。
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { Scene } from "../../api/types";

interface Props {
  sceneId: string;
  scene: Scene;
  onClose: () => void;
}

interface SceneEnvFields {
  time_of_day: string;
  lighting: string;
  weather: string;
  mood: string;
  description: string;
}

export function ScenePropertiesEditor({ sceneId, scene, onClose }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<SceneEnvFields>({
    time_of_day: scene.time_of_day ?? "",
    lighting: scene.lighting ?? "",
    weather: scene.weather ?? "",
    mood: scene.mood ?? "",
    description: scene.description ?? "",
  });
  const [conflict, setConflict] = useState(false);

  const setField = (key: keyof SceneEnvFields, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const dirty =
    form.time_of_day !== (scene.time_of_day ?? "") ||
    form.lighting !== (scene.lighting ?? "") ||
    form.weather !== (scene.weather ?? "") ||
    form.mood !== (scene.mood ?? "") ||
    form.description !== (scene.description ?? "");

  const save = useMutation({
    mutationFn: (patch: SceneEnvFields) =>
      api.patch<Scene>(`/scenes/${sceneId}`, { revision: scene.revision, patch }),
    onSuccess: () => {
      setConflict(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.scene(sceneId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard }); // 场景头 meta 行
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.sceneContinuity }); // 环境基准变化
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.continuityWarnings });
      onClose();
    },
    onError: (error) => {
      // 409 乐观并发冲突：场景已被其他写入者修改 → 提示关闭重开（组件以最新 scene 重新挂载）。
      if (error instanceof Error && /409|CONFLICT/i.test(error.message)) {
        setConflict(true);
      }
    },
  });

  const submit = () => {
    if (!dirty || save.isPending) return;
    save.mutate(form);
  };

  return (
    <div className="scene-props-editor">
      <div className="scene-props-head">
        <span className="section-kicker">场景环境</span>
        <span className="muted small">保存后重新计算连续性并标记受影响镜头待重生成</span>
      </div>
      <div className="scene-props-grid">
        <label className="field">
          <span className="field-label">时段</span>
          <input value={form.time_of_day} placeholder="如：白天 / 夜晚 / 黄昏" onChange={(e) => setField("time_of_day", e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">光照</span>
          <input value={form.lighting} placeholder="如：柔和日光 / 霓虹灯" onChange={(e) => setField("lighting", e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">天气</span>
          <input value={form.weather} placeholder="如：晴 / 雨 / 雪" onChange={(e) => setField("weather", e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">氛围</span>
          <input value={form.mood} placeholder="如：紧张 / 温馨" onChange={(e) => setField("mood", e.target.value)} />
        </label>
        <label className="field scene-props-desc">
          <span className="field-label">场景描述</span>
          <textarea rows={2} value={form.description} placeholder="场景整体描述（供 AI 分析与连续性）" onChange={(e) => setField("description", e.target.value)} />
        </label>
      </div>
      {conflict && (
        <p className="error-text">
          场景已被其他修改更新（409 冲突）——请关闭后重新打开编辑，将载入最新场景信息。
        </p>
      )}
      {save.error && !conflict && <ApiErrorPanel error={save.error} />}
      <div className="scene-props-actions">
        <button className="btn primary tiny" disabled={!dirty || save.isPending} onClick={submit}>
          <Check size={13} /> {save.isPending ? "保存中…" : "保存"}
        </button>
        <button className="btn secondary tiny" onClick={onClose}>
          <X size={13} /> 取消
        </button>
      </div>
    </div>
  );
}
