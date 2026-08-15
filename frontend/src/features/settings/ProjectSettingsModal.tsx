// ProjectSettingsModal (P3): per-project settings form.
// GET /projects/{id}/settings prefills the form; PUT saves a partial update.
// Handles loading / error / saving states and surfaces backend failures via ApiErrorPanel.
// The 0/1 flags (auto_save, continuity_enabled, auto_activate_new_generation) are stored
// as integers by the backend; auto_retry / max_retry_count are small non-negative counts.

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle, SlidersHorizontal, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { ProjectSettingUpdate, ProjectSettings } from "../../api/types";

const LANGUAGE_OPTIONS = ["zh-CN", "zh-TW", "en", "ja", "ko"] as const;

interface SettingsForm {
  language: string;
  default_llm_provider: string;
  default_llm_model: string;
  default_image_provider: string;
  default_image_model: string;
  default_video_provider: string;
  default_video_model: string;
  default_voice_provider: string;
  default_voice_model: string;
  default_image_workflow_id: string;
  default_video_workflow_id: string;
  auto_retry: number;
  max_retry_count: number;
  auto_save: boolean;
  continuity_enabled: boolean;
  auto_activate_new_generation: boolean;
}

function toForm(settings: ProjectSettings): SettingsForm {
  return {
    language: settings.language ?? "zh-CN",
    default_llm_provider: settings.default_llm_provider ?? "",
    default_llm_model: settings.default_llm_model ?? "",
    default_image_provider: settings.default_image_provider ?? "",
    default_image_model: settings.default_image_model ?? "",
    default_video_provider: settings.default_video_provider ?? "",
    default_video_model: settings.default_video_model ?? "",
    default_voice_provider: settings.default_voice_provider ?? "",
    default_voice_model: settings.default_voice_model ?? "",
    default_image_workflow_id: settings.default_image_workflow_id ?? "",
    default_video_workflow_id: settings.default_video_workflow_id ?? "",
    auto_retry: settings.auto_retry,
    max_retry_count: settings.max_retry_count,
    auto_save: settings.auto_save === 1,
    continuity_enabled: settings.continuity_enabled === 1,
    auto_activate_new_generation: settings.auto_activate_new_generation === 1,
  };
}

function toUpdate(form: SettingsForm): ProjectSettingUpdate {
  const str = (value: string) => (value.trim() ? value.trim() : null);
  return {
    language: form.language,
    default_llm_provider: str(form.default_llm_provider),
    default_llm_model: str(form.default_llm_model),
    default_image_provider: str(form.default_image_provider),
    default_image_model: str(form.default_image_model),
    default_video_provider: str(form.default_video_provider),
    default_video_model: str(form.default_video_model),
    default_voice_provider: str(form.default_voice_provider),
    default_voice_model: str(form.default_voice_model),
    default_image_workflow_id: str(form.default_image_workflow_id),
    default_video_workflow_id: str(form.default_video_workflow_id),
    auto_retry: form.auto_retry,
    max_retry_count: form.max_retry_count,
    auto_save: form.auto_save ? 1 : 0,
    continuity_enabled: form.continuity_enabled ? 1 : 0,
    auto_activate_new_generation: form.auto_activate_new_generation ? 1 : 0,
  };
}

interface ProjectSettingsModalProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
}

export function ProjectSettingsModal({ projectId, open, onClose }: ProjectSettingsModalProps) {
  const queryClient = useQueryClient();
  const { data: settings, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.projectSettings(projectId),
    queryFn: () => api.get<ProjectSettings>("/projects/" + projectId + "/settings"),
    enabled: open,
  });
  const [form, setForm] = useState<SettingsForm | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (open) setSaved(false);
  }, [open]);
  useEffect(() => {
    if (settings) setForm(toForm(settings));
  }, [settings]);

  const save = useMutation({
    mutationFn: (update: ProjectSettingUpdate) => api.put<ProjectSettings>("/projects/" + projectId + "/settings", update),
    onSuccess: (updated) => {
      void queryClient.setQueryData<ProjectSettings>(queryKeys.projectSettings(projectId), updated);
      setForm(toForm(updated));
      setSaved(true);
    },
  });

  if (!open) return null;

  const setField = <K extends keyof SettingsForm>(key: K, value: SettingsForm[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  const dirty = form
    ? JSON.stringify(form) !== JSON.stringify(settings ? toForm(settings) : null)
    : false;

  return (
    <div className="settings-modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="settings-modal" role="dialog" aria-modal="true" aria-label="项目设置">
        <header className="settings-modal-head">
          <div><span className="eyebrow">PROJECT SETTINGS</span><h2><SlidersHorizontal size={18} /> 项目设置</h2></div>
          <button type="button" className="icon-button" aria-label="关闭设置" onClick={onClose}><X size={17} /></button>
        </header>

        {isLoading && <p className="muted settings-modal-loading">正在读取项目设置…</p>}
        {isError && <div className="settings-modal-body"><ApiErrorPanel error={error} /><p className="muted small">无法读取设置，请确认 Studio Service 已启动。</p></div>}

        {!isLoading && !isError && form && (
          <div className="settings-modal-body">
            <section className="settings-section">
              <h3>通用</h3>
              <label className="field"><span className="field-label">语言</span>
                <select value={form.language} onChange={(e) => setField("language", e.target.value)}>
                  {LANGUAGE_OPTIONS.map((lang) => <option key={lang} value={lang}>{lang}</option>)}
                </select>
              </label>
            </section>

            <section className="settings-section">
              <h3>LLM</h3>
              <div className="settings-row">
                <label className="field"><span className="field-label">Provider</span>
                  <input value={form.default_llm_provider} placeholder="如 openai / local" onChange={(e) => setField("default_llm_provider", e.target.value)} />
                </label>
                <label className="field"><span className="field-label">Model</span>
                  <input value={form.default_llm_model} placeholder="如 gpt-4o-mini" onChange={(e) => setField("default_llm_model", e.target.value)} />
                </label>
              </div>
            </section>

            <section className="settings-section">
              <h3>图像</h3>
              <div className="settings-row">
                <label className="field"><span className="field-label">Provider</span>
                  <input value={form.default_image_provider} placeholder="如 comfyui / mock" onChange={(e) => setField("default_image_provider", e.target.value)} />
                </label>
                <label className="field"><span className="field-label">Model</span>
                  <input value={form.default_image_model} placeholder="模型名" onChange={(e) => setField("default_image_model", e.target.value)} />
                </label>
              </div>
              <label className="field"><span className="field-label">默认 Workflow</span>
                <input value={form.default_image_workflow_id} placeholder="如 default_image_api" onChange={(e) => setField("default_image_workflow_id", e.target.value)} />
              </label>
            </section>

            <section className="settings-section">
              <h3>视频</h3>
              <div className="settings-row">
                <label className="field"><span className="field-label">Provider</span>
                  <input value={form.default_video_provider} placeholder="视频 Provider" onChange={(e) => setField("default_video_provider", e.target.value)} />
                </label>
                <label className="field"><span className="field-label">Model</span>
                  <input value={form.default_video_model} placeholder="模型名" onChange={(e) => setField("default_video_model", e.target.value)} />
                </label>
              </div>
              <label className="field"><span className="field-label">默认 Workflow</span>
                <input value={form.default_video_workflow_id} placeholder="视频 Workflow" onChange={(e) => setField("default_video_workflow_id", e.target.value)} />
              </label>
            </section>

            <section className="settings-section">
              <h3>配音</h3>
              <div className="settings-row">
                <label className="field"><span className="field-label">Provider</span>
                  <input value={form.default_voice_provider} placeholder="配音 Provider" onChange={(e) => setField("default_voice_provider", e.target.value)} />
                </label>
                <label className="field"><span className="field-label">Model</span>
                  <input value={form.default_voice_model} placeholder="模型名" onChange={(e) => setField("default_voice_model", e.target.value)} />
                </label>
              </div>
            </section>

            <section className="settings-section">
              <h3>生成行为</h3>
              <div className="settings-row">
                <label className="field"><span className="field-label">自动重试次数</span>
                  <input type="number" min={0} value={form.auto_retry} onChange={(e) => setField("auto_retry", Math.max(0, Number(e.target.value) || 0))} />
                </label>
                <label className="field"><span className="field-label">最大重试上限</span>
                  <input type="number" min={0} value={form.max_retry_count} onChange={(e) => setField("max_retry_count", Math.max(0, Number(e.target.value) || 0))} />
                </label>
              </div>
              <ToggleRow label="自动保存" hint="生成完成后自动落库" checked={form.auto_save} onChange={(v) => setField("auto_save", v)} />
              <ToggleRow label="连贯性检查" hint="生成时执行连续性校验" checked={form.continuity_enabled} onChange={(v) => setField("continuity_enabled", v)} />
              <ToggleRow label="新版本自动启用" hint="新生成版本自动设为当前" checked={form.auto_activate_new_generation} onChange={(v) => setField("auto_activate_new_generation", v)} />
            </section>

            {save.isError && <ApiErrorPanel error={save.error} />}
            {saved && (
              <div className="settings-saved-note"><CheckCircle size={16} weight="fill" /> 设置已保存</div>
            )}

            <div className="settings-modal-actions">
              <button type="button" className="btn secondary" onClick={onClose}>取消</button>
              <button type="button" className="btn primary" disabled={!dirty || save.isPending} onClick={() => form && save.mutate(toUpdate(form))}>
                {save.isPending ? "保存中…" : <><Check size={15} /> 保存设置</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ToggleRow({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle-row">
      <span><strong>{label}</strong><small>{hint}</small></span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}
