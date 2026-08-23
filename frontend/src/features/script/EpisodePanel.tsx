import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenText,
  Check,
  CheckCircle,
  CloudCheck,
  FileArrowUp,
  MagicWand,
  MapPin,
  Moon,
  Sparkle,
  UsersThree,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { Episode, Operation, ScenePlan } from "../../api/types";
import { useOperationPolling } from "../ai/useOperationPolling";

export function EpisodePanel({
  episode,
  onScenesCreated,
}: {
  episode: Episode;
  onScenesCreated?: (sceneIds: string[]) => void;
}) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [sourceText, setSourceText] = useState(episode.source_text ?? "");
  const [preview, setPreview] = useState<ScenePlan[] | null>(null);
  const [activePlanIndex, setActivePlanIndex] = useState(0);
  const [previewError, setPreviewError] = useState<Error | null>(null);
  const [createOpId, setCreateOpId] = useState<string | null>(null);

  useEffect(() => {
    setSourceText(episode.source_text ?? "");
    setPreview(null);
    setActivePlanIndex(0);
  }, [episode.id, episode.source_text]);

  const saveSource = useMutation({
    mutationFn: () => api.patch<Episode>(`/episodes/${episode.id}`, { source_text: sourceText }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) }),
  });

  const runPreview = useMutation({
    mutationFn: async () => {
      if (sourceText !== (episode.source_text ?? ""))
        await api.patch<Episode>(`/episodes/${episode.id}`, { source_text: sourceText });
      return api.post<ScenePlan[]>(`/episodes/${episode.id}/analyze/preview`);
    },
    onSuccess: (plans) => {
      setPreview(plans);
      setActivePlanIndex(0);
      setPreviewError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) });
    },
    onError: (error) => setPreviewError(error instanceof Error ? error : new Error(String(error))),
  });

  const createScenes = useMutation({
    mutationFn: () => api.post<{ operation_id: string; status: string }>(`/episodes/${episode.id}/analyze`),
    onSuccess: (response) => setCreateOpId(response.operation_id),
  });

  useOperationPolling(
    createOpId,
    (operation: Operation) => {
      const ids = (operation.result?.created_scene_ids as string[]) ?? [];
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(episode.id) });
      if (ids[0]) onScenesCreated?.(ids);
      setCreateOpId(null);
    },
    (operation) => {
      setPreviewError(new Error(operation.error ?? "创建场景失败"));
      setCreateOpId(null);
    },
  );

  const dirty = sourceText !== (episode.source_text ?? "");
  const activePlan = preview?.[activePlanIndex];
  const wordCount = useMemo(() => sourceText.replace(/\s/g, "").length, [sourceText]);

  // 替换原文 (post-mvp-audit §124): import a local .txt/.md file into the editor.
  // Content lands in the textarea first — the user reviews/saves it (real, recoverable).
  const importFile = (file: File | undefined | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setSourceText(String(reader.result ?? ""));
    reader.onerror = () => setPreviewError(new Error("文件读取失败，请重试。"));
    reader.readAsText(file, "utf-8");
  };

  return (
    <div className={`episode-panel ${preview ? "has-preview" : ""}`}>
      <header className="analysis-header">
        <div>
          <span className="eyebrow">SCRIPT ANALYSIS</span>
          <h1>
            EP{String(episode.episode_number).padStart(2, "0")} · {episode.title || "未命名剧集"}
          </h1>
          <p>
            {wordCount.toLocaleString("zh-CN")} 字 · {episode.status}
          </p>
        </div>
        <div className="analysis-steps">
          <span className="done">
            01 导入 <Check size={13} />
          </span>
          <i />
          <span className={preview ? "done" : "active"}>02 分析 {preview && <Check size={13} />}</span>
          <i />
          <span className={preview ? "active" : ""}>03 检查</span>
          <i />
          <span>04 创建结构</span>
        </div>
      </header>

      <div className="analysis-workspace">
        <section className="source-editor-column">
          <div className="column-header">
            <div>
              <BookOpenText size={18} />
              <strong>小说原文</strong>
            </div>
            <button
              className="btn secondary compact"
              onClick={() => fileRef.current?.click()}
              title="从本地 .txt/.md 文件导入小说原文"
            >
              <FileArrowUp size={15} /> 替换原文
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,text/plain"
              hidden
              onChange={(event) => {
                importFile(event.target.files?.[0]);
                event.target.value = ""; // allow re-importing the same file
              }}
            />
          </div>
          <textarea
            className="source-editor"
            value={sourceText}
            aria-label="小说原文"
            placeholder="粘贴小说章节（1000–3000 字效果最佳）…"
            onChange={(event) => setSourceText(event.target.value)}
          />
          <div className="editor-status">
            <span>
              <CloudCheck size={16} /> {dirty ? "有未保存修改" : "已保存"}
            </span>
            <span>{wordCount.toLocaleString("zh-CN")} 字</span>
          </div>
        </section>

        {preview ? (
          <>
            <section className="scene-plan-column">
              <div className="analysis-result-bar">
                <CheckCircle size={17} weight="fill" />
                <strong>分析完成</strong>
                <span>{preview.length} 个场景</span>
              </div>
              <div className="scene-plan-list">
                {preview.map((plan, index) => (
                  <button
                    key={`${plan.scene_number}-${plan.title}`}
                    className={`scene-plan-card ${index === activePlanIndex ? "active" : ""}`}
                    onClick={() => setActivePlanIndex(index)}
                  >
                    <div>
                      <span>SC{String(plan.scene_number).padStart(2, "0")}</span>
                      <strong>{plan.title}</strong>
                    </div>
                    <p>{plan.description}</p>
                    <small>
                      {plan.location} · {plan.time ?? "未定"}
                    </small>
                  </button>
                ))}
              </div>
            </section>

            <aside className="scene-detail-column">
              <span className="eyebrow">SCENE BREAKDOWN</span>
              <h2>SC{String(activePlan?.scene_number ?? 0).padStart(2, "0")} 场景解构</h2>
              <div className="scene-fact-grid">
                <div>
                  <span>
                    <MapPin size={14} /> 地点
                  </span>
                  <strong>{activePlan?.location ?? "—"}</strong>
                </div>
                <div>
                  <span>
                    <Moon size={14} /> 时间
                  </span>
                  <strong>{activePlan?.time ?? "—"}</strong>
                </div>
                <div>
                  <span>
                    <Sparkle size={14} /> 情绪
                  </span>
                  <strong>{activePlan?.mood ?? "—"}</strong>
                </div>
                <div>
                  <span>
                    <MagicWand size={14} /> 预计镜头
                  </span>
                  <strong>AI 创建后确定</strong>
                </div>
              </div>
              <div className="scene-description-block">
                <span className="field-label">场景描述</span>
                <p>{activePlan?.description}</p>
              </div>
              <div className="scene-description-block muted-block">
                <span className="field-label">
                  <UsersThree size={14} /> 角色提取
                </span>
                <p>角色关系将在确认创建场景后进入 Project State。</p>
              </div>
            </aside>
          </>
        ) : (
          <section className="analysis-start-panel">
            <div className="analysis-orbit">
              <MagicWand size={30} weight="fill" />
            </div>
            <span className="eyebrow">STRUCTURED OUTPUT</span>
            <h2>把原文拆成可制作的场景</h2>
            <p>AI 将识别场景、地点、时间、情绪与剧情节点。预览不会写入 Project State。</p>
            <ul>
              <li>
                <CheckCircle size={16} /> 先预览，再确认创建
              </li>
              <li>
                <CheckCircle size={16} /> 1000–3000 字效果最佳
              </li>
              <li>
                <CheckCircle size={16} /> 重复确认不重复创建场景
              </li>
              <li>
                <CheckCircle size={16} /> 原文变化时替换旧 AI 场景，手动场景保留
              </li>
            </ul>
          </section>
        )}
      </div>

      {previewError && <ApiErrorPanel error={previewError} />}

      <footer className="analysis-footer">
        <div className="row gap">
          <button
            className="btn secondary"
            disabled={!dirty || saveSource.isPending}
            onClick={() => saveSource.mutate()}
          >
            {saveSource.isPending ? "保存中…" : dirty ? "保存剧本" : "已保存"}
          </button>
          {preview && (
            <button className="btn secondary" onClick={() => setPreview(null)}>
              返回修改原文
            </button>
          )}
        </div>
        {preview ? (
          <button
            className="btn primary"
            disabled={createScenes.isPending || Boolean(createOpId)}
            onClick={() => createScenes.mutate()}
          >
            {createScenes.isPending || createOpId ? "正在创建…" : `确认并创建 ${preview.length} 个场景`}
          </button>
        ) : (
          <button
            className="btn primary"
            disabled={!sourceText.trim() || runPreview.isPending}
            onClick={() => runPreview.mutate()}
          >
            <MagicWand size={16} weight="fill" /> {runPreview.isPending ? "AI 分析中…" : "AI 分析并预览"}
          </button>
        )}
      </footer>
    </div>
  );
}
