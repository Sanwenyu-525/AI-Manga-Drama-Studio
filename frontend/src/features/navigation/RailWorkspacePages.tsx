import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowsClockwise,
  Brain,
  FilmStrip,
  MagicWand,
  ShieldCheck,
  SquaresFour,
  UsersThree,
} from "@phosphor-icons/react";
import { Link, Navigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type {
  AgentContinuityRun,
  ContinuityWarning,
  ProjectBootstrap,
  ProjectTreeRead,
  SceneTreeItem,
} from "../../api/types";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { ContinuityWarningList } from "../continuity/ContinuityWarningList";
import { CharactersSection } from "../libraries/CharactersSection";
import { DocumentsSection } from "../libraries/DocumentsSection";
import { canonicalScriptPath, canonicalShotPath, canonicalStoryboardPath } from "../studio/studioRoute";

function useProjectId(): string {
  return useParams().projectId ?? "";
}

function ModuleHeader({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return (
    <header className="rail-module-header">
      <span className="rail-module-icon" aria-hidden>
        {icon}
      </span>
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </header>
  );
}

export function DirectorWorkspacePage() {
  const projectId = useProjectId();
  const setRightPanelTab = useWorkspaceStore((state) => state.setRightPanelTab);
  const setRightPanelCollapsed = useWorkspaceStore((state) => state.setRightPanelCollapsed);
  const { data } = useQuery({
    queryKey: queryKeys.bootstrap(projectId),
    queryFn: () => api.get<ProjectBootstrap>(`/projects/${projectId}/bootstrap`),
    enabled: Boolean(projectId),
  });

  // A deep link must open the same Director surface as a rail click.
  useEffect(() => {
    setRightPanelTab("director");
    setRightPanelCollapsed(false);
  }, [setRightPanelCollapsed, setRightPanelTab]);

  return (
    <div className="rail-module-page">
      <ModuleHeader
        icon={<MagicWand size={22} weight="fill" />}
        title="AI导演"
        description="表达制作目标、检查执行计划，并在右侧导演面板审批对项目状态的修改。"
      />
      <section className="rail-module-panel director-home">
        <div>
          <span className="eyebrow">当前状态</span>
          <strong>{data?.active_agent_runs ? `${data.active_agent_runs} 个任务运行中` : "导演待命"}</strong>
          <p className="muted small">AI 导演始终读取当前项目、剧集、场景和镜头选择；所有修改先形成可审批 Proposal。</p>
        </div>
        <div className="rail-module-actions">
          <Link className="btn secondary compact" to={`/projects/${projectId}/script`}>
            打开故事
          </Link>
          <Link className="btn secondary compact" to={`/projects/${projectId}/storyboard`}>
            打开分镜
          </Link>
          <Link className="btn secondary compact" to={`/projects/${projectId}/continuity`}>
            检查连续性
          </Link>
        </div>
      </section>
    </div>
  );
}

export function CharactersWorkspacePage() {
  const projectId = useProjectId();
  return (
    <div className="rail-module-page characters-workspace">
      <ModuleHeader
        icon={<UsersThree size={22} weight="fill" />}
        title="角色"
        description="管理角色设定、视觉提示词、参考资产版本与当前 MASTER。"
      />
      <section className="rail-module-panel character-library-panel">
        <CharactersSection projectId={projectId} />
      </section>
    </div>
  );
}

function useProjectTree(projectId: string) {
  return useQuery({
    queryKey: queryKeys.projectTree(projectId),
    queryFn: () => api.get<ProjectTreeRead>(`/projects/${projectId}/tree`),
    enabled: Boolean(projectId),
  });
}

export function StoryboardIndexPage() {
  const projectId = useProjectId();
  const tree = useProjectTree(projectId);
  const sceneCount = (tree.data?.episodes ?? []).reduce((count, episode) => count + episode.scenes.length, 0);
  const firstScene = tree.data?.episodes.flatMap((episode) =>
    episode.scenes.map((scene) => ({ episodeId: episode.id, scene })),
  )[0];

  if (!tree.isLoading && !tree.isError && firstScene) {
    return <Navigate to={canonicalStoryboardPath(projectId, firstScene.episodeId, firstScene.scene.id)} replace />;
  }

  return (
    <div className="rail-module-page">
      <ModuleHeader
        icon={<SquaresFour size={22} weight="fill" />}
        title="分镜"
        description="按剧集和场景选择分镜板；场景内可继续生成、排序与审阅镜头。"
      />
      {tree.isLoading && <div className="workspace-loading">正在读取分镜索引…</div>}
      {tree.isError && <ApiErrorPanel error={tree.error as never} />}
      {!tree.isLoading && !tree.isError && sceneCount === 0 && (
        <div className="empty-state rail-module-empty">
          <SquaresFour size={32} />
          <h2>还没有可用场景</h2>
          <p>先在故事模块导入原文并创建场景，再回到这里制作分镜。</p>
          <Link className="btn primary compact" to={`/projects/${projectId}/script`}>
            前往故事
          </Link>
        </div>
      )}
      <div className="rail-index-groups">
        {(tree.data?.episodes ?? []).map((episode) => (
          <section className="rail-index-group" key={episode.id}>
            <div className="rail-index-heading">
              <strong>
                EP{String(episode.episode_number).padStart(2, "0")} · {episode.title || "未命名"}
              </strong>
              <span className="muted small">{episode.scene_count} 场</span>
            </div>
            {episode.scenes.length === 0 ? (
              <Link className="rail-index-empty" to={canonicalScriptPath(projectId, episode.id)}>
                该集还没有场景 · 前往故事创建
              </Link>
            ) : (
              <ul className="rail-index-list">
                {episode.scenes.map((scene) => (
                  <li key={scene.id}>
                    <Link to={canonicalStoryboardPath(projectId, episode.id, scene.id)}>
                      <span className="mono">SC{String(scene.scene_number).padStart(2, "0")}</span>
                      <span>{scene.name || "未命名场景"}</span>
                      <span className="muted small">{scene.shot_count} 镜</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

export function ShotsIndexPage() {
  const projectId = useProjectId();
  const tree = useProjectTree(projectId);
  const shots = useMemo(
    () =>
      (tree.data?.episodes ?? []).flatMap((episode) =>
        episode.scenes.flatMap((scene) => scene.shots.map((shot) => ({ episode, scene, shot }))),
      ),
    [tree.data],
  );

  return (
    <div className="rail-module-page">
      <ModuleHeader
        icon={<FilmStrip size={22} weight="fill" />}
        title="镜头"
        description="浏览项目全部镜头，并打开所在分镜板与右侧镜头检查器。"
      />
      {tree.isLoading && <div className="workspace-loading">正在读取镜头索引…</div>}
      {tree.isError && <ApiErrorPanel error={tree.error as never} />}
      {!tree.isLoading && !tree.isError && shots.length === 0 && (
        <div className="empty-state rail-module-empty">
          <FilmStrip size={32} />
          <h2>还没有镜头</h2>
          <p>先进入分镜模块选择场景，再手动添加或使用 AI 生成镜头。</p>
          <Link className="btn primary compact" to={`/projects/${projectId}/storyboard`}>
            前往分镜
          </Link>
        </div>
      )}
      {shots.length > 0 && (
        <div className="rail-shot-table" role="table" aria-label="项目镜头">
          <div className="rail-shot-row heading" role="row">
            <span>镜头</span>
            <span>场景</span>
            <span>类型</span>
            <span>状态</span>
            <span>版本</span>
          </div>
          {shots.map(({ episode, scene, shot }) => (
            <Link
              className="rail-shot-row"
              role="row"
              key={shot.id}
              to={canonicalShotPath(projectId, episode.id, scene.id, shot.id)}
            >
              <strong className="mono">SH{String(shot.shot_number).padStart(3, "0")}</strong>
              <span className="ellipsis">
                EP{String(episode.episode_number).padStart(2, "0")} / SC{String(scene.scene_number).padStart(2, "0")} ·{" "}
                {scene.name || "未命名"}
              </span>
              <span>{shot.shot_type || "—"}</span>
              <span className="badge neutral">{shotStatusLabel(shot.status)}</span>
              <span className="mono muted">{shot.active_image_version ? `V${shot.active_image_version}` : "—"}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function shotStatusLabel(status: string): string {
  return (
    ({ draft: "草稿", image_ready: "已出图", approved: "已确认", failed: "失败" } as Record<string, string>)[status] ??
    status ??
    "等待"
  );
}

export function KnowledgeWorkspacePage() {
  const projectId = useProjectId();
  return (
    <div className="rail-module-page knowledge-workspace">
      <ModuleHeader
        icon={<Brain size={22} weight="fill" />}
        title="知识库"
        description="集中管理项目设定文档（人物设定/世界观/大纲/小说原稿）——AI 分析时按预算引用这些事实。"
      />
      <section className="rail-module-panel knowledge-library-panel">
        <DocumentsSection projectId={projectId} />
      </section>
      <div className="rail-module-actions knowledge-footer-actions">
        <Link className="btn secondary compact" to={`/projects/${projectId}/source`}>
          查看源内容
        </Link>
        <Link className="btn secondary compact" to={`/projects/${projectId}/prompts`}>
          查看提示词历史
        </Link>
      </div>
    </div>
  );
}

interface SceneRef extends SceneTreeItem {
  episodeId: string;
  episodeNumber: number;
}

export function ContinuityWorkspacePage() {
  const projectId = useProjectId();
  const queryClient = useQueryClient();
  const tree = useProjectTree(projectId);
  const scenes = useMemo<SceneRef[]>(
    () =>
      (tree.data?.episodes ?? []).flatMap((episode) =>
        episode.scenes.map((scene) => ({
          ...scene,
          episodeId: episode.id,
          episodeNumber: episode.episode_number,
        })),
      ),
    [tree.data],
  );
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const selected = scenes.find((scene) => scene.id === selectedSceneId) ?? scenes[0] ?? null;
  const warnings = useQuery({
    queryKey: queryKeys.continuityWarnings(selected?.id ?? "__none__"),
    queryFn: () => api.get<ContinuityWarning[]>(`/scenes/${selected?.id}/continuity-warnings`),
    enabled: Boolean(selected),
  });
  const recompute = useMutation({
    mutationFn: () => api.post(`/scenes/${selected?.id}/continuity/recompute`),
    onSuccess: () => {
      if (selected) void queryClient.invalidateQueries({ queryKey: queryKeys.continuityWarnings(selected.id) });
    },
  });
  const semanticCheck = useMutation({
    mutationFn: () => api.post<AgentContinuityRun>("/agent/continuity/check", { scene_id: selected?.id }),
    onSuccess: () => {
      if (selected) void queryClient.invalidateQueries({ queryKey: queryKeys.continuityWarnings(selected.id) });
    },
  });

  return (
    <div className="rail-module-page continuity-workspace">
      <ModuleHeader
        icon={<ShieldCheck size={22} weight="fill" />}
        title="连续性检查"
        description="按场景检查人物、环境、道具与镜头衔接，并把修复交给 AI 导演审批。"
      />
      {tree.isLoading && <div className="workspace-loading">正在读取场景…</div>}
      {tree.isError && <ApiErrorPanel error={tree.error as never} />}
      {!tree.isLoading && !tree.isError && scenes.length === 0 && (
        <div className="empty-state rail-module-empty">
          <ShieldCheck size={32} />
          <h2>还没有可检查的场景</h2>
          <p>创建场景和镜头后，连续性状态与警告会显示在这里。</p>
        </div>
      )}
      {selected && (
        <div className="continuity-layout">
          <aside className="continuity-scene-list" aria-label="场景列表">
            {scenes.map((scene) => (
              <button
                type="button"
                key={scene.id}
                className={scene.id === selected.id ? "active" : ""}
                aria-current={scene.id === selected.id ? "page" : undefined}
                onClick={() => setSelectedSceneId(scene.id)}
              >
                <span className="mono">
                  EP{String(scene.episodeNumber).padStart(2, "0")} / SC{String(scene.scene_number).padStart(2, "0")}
                </span>
                <span className="ellipsis">{scene.name || "未命名场景"}</span>
              </button>
            ))}
          </aside>
          <section className="rail-module-panel continuity-detail">
            <div className="rail-index-heading">
              <div>
                <strong>{selected.name || "未命名场景"}</strong>
                <span className="muted small"> · {selected.shot_count} 镜</span>
              </div>
              <div className="rail-module-actions">
                <Link
                  className="btn secondary compact"
                  to={canonicalStoryboardPath(projectId, selected.episodeId, selected.id)}
                >
                  打开分镜
                </Link>
                <button
                  className="btn secondary compact"
                  disabled={recompute.isPending}
                  onClick={() => recompute.mutate()}
                >
                  <ArrowsClockwise size={13} /> {recompute.isPending ? "重算中…" : "重新计算"}
                </button>
                <button
                  className="btn primary compact"
                  disabled={semanticCheck.isPending}
                  onClick={() => semanticCheck.mutate()}
                >
                  <MagicWand size={13} /> {semanticCheck.isPending ? "检测中…" : "AI 语义检测"}
                </button>
              </div>
            </div>
            {warnings.isLoading && <div className="workspace-loading">正在读取连续性警告…</div>}
            {warnings.isError && <ApiErrorPanel error={warnings.error as never} />}
            {!warnings.isLoading && !warnings.isError && (warnings.data ?? []).length === 0 && (
              <div className="continuity-clean-state">
                <ShieldCheck size={24} weight="fill" />
                <div>
                  <strong>当前没有开放警告</strong>
                  <p className="muted small">可重新计算确定性规则，或运行 AI 语义检测。</p>
                </div>
              </div>
            )}
            <ContinuityWarningList warnings={warnings.data ?? []} sceneId={selected.id} />
          </section>
        </div>
      )}
    </div>
  );
}
