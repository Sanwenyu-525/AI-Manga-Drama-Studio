import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenText,
  Check,
  CheckCircle,
  CloudCheck,
  FileArrowUp,
  FileText,
  Folder,
  FolderOpen,
  MagicWand,
  MapPin,
  Moon,
  Plus,
  Sparkle,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { Episode, Operation, ScenePlan } from "../../api/types";
import { isTauriRuntime, listTextDir, pickDirectory, pickTextFile, readTextFile } from "../../lib/nativeDialog";
import { useOperationPolling } from "../ai/useOperationPolling";
import { PipelineBar } from "../pipeline/PipelineBar";
import { canonicalScriptPath } from "../studio/studioRoute";

// AI 分析等待期轮换提示：只描述真实在发生的阶段，不伪造进度百分比。
const ANALYSIS_HINTS = [
  "正在连接模型…",
  "正在读取原文语义与结构…",
  "正在识别场景、地点与情绪节拍…",
  "正在生成结构化场景草案…",
];

// P2-E1-T01: preview/confirm 响应信封（后端落库不可变快照）。
interface PreviewResponse {
  snapshot_id: string;
  episode_id: string;
  source_hash: string;
  plans: ScenePlan[];
  model: string | null;
  status: string;
}
interface LatestSnapshot {
  id: string;
  status: "pending" | "confirmed" | "expired";
  plans: ScenePlan[];
  episode_revision: number;
  created_scene_ids: string[];
}

function formatElapsed(total: number): string {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m} 分 ${String(s).padStart(2, "0")} 秒` : `${s} 秒`;
}

// 浏览器环境读取本地文本（FileReader promise 化）；Tauri 壳改走 Rust 命令。
function readBrowserFile(file: File | undefined | null): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("no file"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("FileReader failed"));
    reader.readAsText(file, "utf-8");
  });
}

// 分析进行中的右侧面板：骨架屏 + 真实耗时，替代静默等待（LLM 调用常达 1 分钟+）。
function AnalysisLoadingPanel({ elapsed }: { elapsed: number }) {
  const hint = ANALYSIS_HINTS[Math.min(Math.floor(elapsed / 5), ANALYSIS_HINTS.length - 1)];
  return (
    <section className="analysis-start-panel analysis-loading-panel" role="status" aria-live="polite">
      <div className="analysis-orbit analysis-orbit--live">
        <MagicWand size={30} weight="fill" />
      </div>
      <span className="eyebrow">结构化输出</span>
      <h2>AI 正在分析原文</h2>
      <p className="analysis-loading-status">
        {hint}
        <span className="loading-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
      </p>
      <p className="analysis-loading-elapsed">已进行 {formatElapsed(elapsed)} · 长文本通常需要 1–2 分钟</p>
      <div className="scene-skeleton-list" aria-hidden>
        {[0, 1, 2].map((i) => (
          <div className="scene-skeleton" key={i} style={{ animationDelay: `${i * 0.18}s` }}>
            <span className="sk-line sk-title" />
            <span className="sk-line" />
            <span className="sk-line sk-short" />
          </div>
        ))}
      </div>
    </section>
  );
}

export function EpisodePanel({
  episode,
  onScenesCreated,
}: {
  episode: Episode;
  onScenesCreated?: (sceneIds: string[]) => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const dirRef = useRef<HTMLInputElement>(null);
  const [sourceText, setSourceText] = useState(episode.source_text ?? "");

  // 剧集切换/新建：资源树移除后这里是唯一的剧集级入口（缓存与 StudioPage 共享）。
  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(episode.project_id),
    queryFn: () => api.get<Episode[]>(`/projects/${episode.project_id}/episodes`),
    staleTime: 30_000,
  });
  const createEpisode = useMutation({
    mutationFn: () =>
      api.post<Episode>(`/projects/${episode.project_id}/episodes`, {
        title: "第 " + ((episodes?.length ?? 0) + 1) + " 集",
      }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) });
      navigate(canonicalScriptPath(episode.project_id, created.id));
    },
  });
  // 原稿目录工作区：选择一个本地目录，列出其中的 .txt/.md 文件，点选即读入原文。
  // 全部在本地完成（Tauri 壳经 Rust 命令只读，浏览器经 FileReader/webkitdirectory），
  // 不落后端、不存路径（安全且无需 API）。红线：导入永远经用户在 UI 操作。
  const [workspaceFiles, setWorkspaceFiles] = useState<{ path: string; file?: File; absPath?: string }[]>([]);
  const [workspaceDirName, setWorkspaceDirName] = useState<string | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [loadingFile, setLoadingFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<ScenePlan[] | null>(null);
  // P2-E1-T01: 预览落库的不可变快照 id——confirm 只提交它，后端零二次 LLM。
  const [snapshotId, setSnapshotId] = useState<string | null>(null);
  const [activePlanIndex, setActivePlanIndex] = useState(0);
  const [previewError, setPreviewError] = useState<Error | null>(null);
  const [createOpId, setCreateOpId] = useState<string | null>(null);

  useEffect(() => {
    setSourceText(episode.source_text ?? "");
    setPreview(null);
    setSnapshotId(null);
    setActivePlanIndex(0);
  }, [episode.id, episode.source_text]);

  // P2-E1-T01 刷新水合：重开页面时恢复最近一次 pending 快照（AC: 刷新后可读取 preview 状态）。
  const { data: latestSnapshot } = useQuery({
    queryKey: ["analysis-snapshot", episode.id],
    queryFn: () => api.get<LatestSnapshot | null>(`/episodes/${episode.id}/analysis-snapshots/latest`),
    enabled: !preview && !createOpId,
  });
  useEffect(() => {
    if (!preview && latestSnapshot && latestSnapshot.status === "pending") {
      setPreview(latestSnapshot.plans);
      setSnapshotId(latestSnapshot.id);
    }
  }, [preview, latestSnapshot]);

  // Save the novel text through the §21/§88 optimistic-concurrency envelope
  // ({revision, patch}); refresh the cached revision from the response so back-
  // to-back saves don't 409, and translate a lost race into an actionable hint.
  const saveSourceText = async (): Promise<Episode> => {
    try {
      const updated = await api.patch<Episode>(`/episodes/${episode.id}`, {
        revision: episode.revision,
        patch: { source_text: sourceText },
      });
      queryClient.setQueryData<Episode[]>(queryKeys.episodes(episode.project_id), (prev) =>
        (prev ?? []).map((item) =>
          item.id === updated.id
            ? { ...item, source_text: updated.source_text, revision: updated.revision, updated_at: updated.updated_at }
            : item,
        ),
      );
      return updated;
    } catch (error) {
      if (error instanceof ApiError && error.code === "CONFLICT") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) });
        throw new Error("该剧集刚被其他修改更新过，已刷新为最新内容，请重试保存。", { cause: error });
      }
      throw error;
    }
  };

  const saveSource = useMutation({
    mutationFn: saveSourceText,
    onSuccess: () => {
      setPreviewError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) });
    },
    onError: (error) => setPreviewError(error instanceof Error ? error : new Error(String(error))),
  });

  const runPreview = useMutation({
    mutationFn: async () => {
      if (sourceText !== (episode.source_text ?? "")) await saveSourceText();
      // P2-E1-T01: preview 落库不可变快照；返回 {snapshot_id, plans}。
      return api.post<PreviewResponse>(`/episodes/${episode.id}/analyze/preview`);
    },
    onSuccess: (response) => {
      setPreview(response.plans);
      setSnapshotId(response.snapshot_id);
      setActivePlanIndex(0);
      setPreviewError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) });
      void queryClient.invalidateQueries({ queryKey: ["analysis-snapshot", episode.id] });
    },
    onError: (error) => setPreviewError(error instanceof Error ? error : new Error(String(error))),
  });

  // 分析等待计时：驱动右侧加载面板的耗时与轮换提示（真实时间，不伪造进度）。
  const [previewElapsed, setPreviewElapsed] = useState(0);
  useEffect(() => {
    if (!runPreview.isPending) {
      setPreviewElapsed(0);
      return;
    }
    const started = Date.now();
    const timer = window.setInterval(() => setPreviewElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [runPreview.isPending]);

  // P2-E1-T01: confirm 只提交快照 id——写入的正是预览看到的计划（无二次 LLM）。
  // 原文已变时后端返回失败（快照过期），提示重新预览。
  const createScenes = useMutation({
    mutationFn: () =>
      api.post<{ operation_id: string; status: string }>(`/episodes/${episode.id}/analyze`, {
        snapshot_id: snapshotId ?? undefined,
      }),
    onSuccess: (response) => setCreateOpId(response.operation_id),
    onError: (error) => setPreviewError(error instanceof Error ? error : new Error(String(error))),
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
  // 方案 B：Tauri 壳走原生文件选择 + Rust 只读命令；浏览器回落 FileReader。
  const importFile = async (file?: File | null) => {
    if (isTauriRuntime()) {
      try {
        const picked = await pickTextFile("选择小说原文（.txt/.md）");
        if (!picked) return;
        setSourceText(await readTextFile(picked));
      } catch (err) {
        setPreviewError(err instanceof Error ? err : new Error("文件读取失败，请重试。"));
      }
      return;
    }
    if (!file) return;
    try {
      setSourceText(await readBrowserFile(file));
    } catch {
      setPreviewError(new Error("文件读取失败，请重试。"));
    }
  };

  // 原稿目录工作区：选择一个本地目录，列出其中的文本稿文件供点选读入。
  const TEXT_EXT = /\.(txt|md|markdown|text)$/i;
  const pickWorkspaceDir = async (files?: FileList | null) => {
    if (isTauriRuntime()) {
      try {
        const dir = await pickDirectory("选择原稿目录（.txt/.md）");
        if (!dir) return;
        const entries = await listTextDir(dir);
        const picked = entries.slice(0, 200).map((e) => ({ path: e.path, absPath: e.abs_path }));
        setWorkspaceFiles(picked);
        setWorkspaceDirName(dir.split(/[\\/]/).filter(Boolean).pop() ?? dir);
        setWorkspaceOpen(picked.length > 0);
        if (!picked.length) setPreviewError(new Error("该目录里没有找到 .txt / .md 文本文件。"));
      } catch (err) {
        setPreviewError(err instanceof Error ? err : new Error("读取目录失败，请重试。"));
      }
      return;
    }
    if (!files) return;
    const picked = Array.from(files)
      .filter((f) => f.webkitRelativePath && TEXT_EXT.test(f.name))
      .map((f) => ({ path: f.webkitRelativePath, file: f }))
      .sort((a, b) => a.path.localeCompare(b.path))
      .slice(0, 200);
    setWorkspaceFiles(picked);
    setWorkspaceDirName(picked[0]?.path.split("/")[0] ?? null);
    setWorkspaceOpen(picked.length > 0);
    if (!picked.length) setPreviewError(new Error("该目录里没有找到 .txt / .md 文本文件。"));
  };

  const loadWorkspaceFile = async (item: { path: string; file?: File; absPath?: string }) => {
    setLoadingFile(item.path);
    try {
      const text = item.absPath ? await readTextFile(item.absPath) : await readBrowserFile(item.file);
      setSourceText(text);
    } catch {
      setPreviewError(new Error(`读取「${item.path}」失败，请重试。`));
    } finally {
      setLoadingFile(null);
    }
  };

  // 打开入口：Tauri 壳直接调原生选择器（经 Rust 只读命令），浏览器回落隐藏 file input。
  const openWorkspaceDir = () => {
    if (isTauriRuntime()) {
      void pickWorkspaceDir();
    } else {
      dirRef.current?.click();
    }
  };
  const openReplaceFile = () => {
    if (isTauriRuntime()) {
      void importFile();
    } else {
      fileRef.current?.click();
    }
  };

  // C2 一键成片：pipeline 分析确认复用现有 preview 展示卡（plans + snapshot）。
  const showPipelinePlans = (plans: ScenePlan[], pipelineSnapshotId: string | null) => {
    setPreview(plans);
    setSnapshotId(pipelineSnapshotId);
    setActivePlanIndex(0);
    setPreviewError(null);
  };

  return (
    <div className={`episode-panel ${preview ? "has-preview" : ""}`}>
      <header className="analysis-header">
        <div>
          <span className="eyebrow">剧本分析</span>
          <h1>
            EP{String(episode.episode_number).padStart(2, "0")} · {episode.title || "未命名剧集"}
          </h1>
          <div className="episode-heading-actions">
            {episodes?.length ? (
              <select
                className="episode-switch"
                value={episode.id}
                onChange={(e) => navigate(canonicalScriptPath(episode.project_id, e.target.value))}
                aria-label="切换剧集"
              >
                {episodes.map((item) => (
                  <option key={item.id} value={item.id}>
                    EP{String(item.episode_number).padStart(2, "0")} · {item.title || "未命名剧集"}
                  </option>
                ))}
              </select>
            ) : null}
            <button
              type="button"
              className="btn secondary compact"
              disabled={createEpisode.isPending}
              onClick={() => createEpisode.mutate()}
              title="新建一集空白剧集"
            >
              <Plus size={13} /> {createEpisode.isPending ? "创建中…" : "新建剧集"}
            </button>
          </div>
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

      <PipelineBar episode={episode} onShowPlans={showPipelinePlans} />

      <div className="analysis-workspace">
        <section className="source-editor-column">
          <div className="column-header">
            <div>
              <BookOpenText size={18} />
              <strong>小说原文</strong>
              {workspaceDirName && (
                <button
                  type="button"
                  className="workspace-dir-chip"
                  title="切换工作区目录"
                  onClick={openWorkspaceDir}
                >
                  <Folder size={14} /> {workspaceDirName}
                </button>
              )}
            </div>
            <div className="row gap">
              <button
                className={`btn secondary compact ${workspaceFiles.length ? "workspace-active" : ""}`}
                onClick={openWorkspaceDir}
                title="选择一个本地目录，列出其中的小说原稿文件供点选读入"
              >
                <FolderOpen size={15} /> 原稿目录
              </button>
              <button
                className="btn secondary compact"
                onClick={openReplaceFile}
                title="从本地 .txt/.md 文件导入小说原文"
              >
                <FileArrowUp size={15} /> 替换原文
              </button>
            </div>
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
            <input
              ref={dirRef}
              type="file"
              // @ts-expect-error webkitdirectory 是目录选择扩展属性，未被 TS 声明
              webkitdirectory=""
              multiple
              hidden
              onChange={(event) => {
                pickWorkspaceDir(event.target.files);
                event.target.value = ""; // allow re-picking the same dir
              }}
            />
          </div>
          {workspaceOpen && workspaceFiles.length > 0 && (
            <div className="workspace-files">
              <div className="workspace-files-head">
                <span>
                  <FolderOpen size={13} /> 原稿目录 · {workspaceFiles.length} 个文件
                </span>
                <button type="button" className="text-action" onClick={() => setWorkspaceOpen(false)}>
                  <X size={13} /> 收起
                </button>
              </div>
              <div className="workspace-files-list">
                {workspaceFiles.map((item) => (
                  <button
                    key={item.path}
                    type="button"
                    className="workspace-file-row"
                    disabled={loadingFile === item.path}
                    onClick={() => loadWorkspaceFile(item)}
                    title={`读入 ${item.path}`}
                  >
                    <FileText size={13} />
                    <span>{item.path}</span>
                    {loadingFile === item.path && <span className="muted small">读取中…</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
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
              <span className="eyebrow">场景拆解</span>
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
        ) : runPreview.isPending ? (
          <AnalysisLoadingPanel elapsed={previewElapsed} />
        ) : (
          <section className="analysis-start-panel">
            <span className="eyebrow">结构化输出</span>
            <h2>把原文拆成可制作的场景</h2>
            <p>AI 将识别场景、地点、时间与情绪节拍；预览不会写入 Project State。先预览，再确认创建。</p>
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
            {runPreview.isPending ? (
              <span className="btn-spinner" aria-hidden />
            ) : (
              <MagicWand size={16} weight="fill" />
            )}{" "}
            {runPreview.isPending ? "AI 分析中…" : "AI 分析并预览"}
          </button>
        )}
      </footer>
    </div>
  );
}
