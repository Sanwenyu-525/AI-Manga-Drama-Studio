import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  Check,
  Circle,
  CheckCircle,
  DotsThree,
  FolderOpen,
  PencilSimple,
  Plus,
  Play,
  SlidersHorizontal,
  Trash,
  X,
} from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { formatDateTime, formatMonthDay } from "../../lib/format";
import { mediaUrl } from "../../lib/mediaUrl";
import type { Episode, Project, ProjectBootstrap, ProjectTreeRead, ProjectUpdateRequest } from "../../api/types";
import { derivePipeline, summarizeEpisodes, type PipelineStage } from "../../lib/workspaceMetrics";

const statusLabel: Record<string, string> = {
  active: "制作中",
  draft: "准备中",
  completed: "已完成",
  archived: "已归档",
};

export function ProjectHome() {
  const queryClient = useQueryClient();
  const coverInputRef = useRef<HTMLInputElement>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) setFilterOpen(false);
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpenId(null);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setFilterOpen(false);
        setMenuOpenId(null);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, []);
  const {
    data: projects,
    isLoading,
    isError,
  } = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<Project[]>("/projects"),
  });

  useEffect(() => {
    if (!activeId && projects?.[0]) setActiveId(projects[0].id);
  }, [activeId, projects]);

  const filteredProjects = useMemo(
    () => (statusFilter === "all" ? (projects ?? []) : (projects ?? []).filter((p) => p.status === statusFilter)),
    [projects, statusFilter],
  );

  const activeProject = useMemo(
    () => filteredProjects.find((project) => project.id === activeId) ?? filteredProjects[0],
    [activeId, filteredProjects],
  );

  const filterCount = filteredProjects.length;
  const activeProjectId = activeProject?.id ?? "";

  // 项目进度来自真实 Project State（与漫剧工作区同一套聚合，不伪造进度）。
  const { data: tree } = useQuery({
    queryKey: queryKeys.projectTree(activeProjectId),
    queryFn: () => api.get<ProjectTreeRead>(`/projects/${activeProjectId}/tree`),
    enabled: Boolean(activeProjectId),
  });
  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(activeProjectId),
    queryFn: () => api.get<Episode[]>(`/projects/${activeProjectId}/episodes`),
    enabled: Boolean(activeProjectId),
  });
  const { data: bootstrap } = useQuery({
    queryKey: queryKeys.bootstrap(activeProjectId),
    queryFn: () => api.get<ProjectBootstrap>(`/projects/${activeProjectId}/bootstrap`),
    enabled: Boolean(activeProjectId),
    staleTime: 10_000,
  });

  const progress = useMemo(() => summarizeEpisodes(tree, episodes), [tree, episodes]);
  const hasTimeline = (bootstrap?.episodes ?? []).some((ep) => ep.has_timeline);
  const hasFinalVideo = (bootstrap?.episodes ?? []).some((ep) => ep.has_final_video);
  const firstEpisodeId = bootstrap?.episodes?.[0]?.id ?? tree?.episodes?.[0]?.id ?? null;

  const pipeline = useMemo<PipelineStage[]>(() => {
    const stages = derivePipeline(progress, hasTimeline, hasFinalVideo);
    // 每阶段补充真实计数 detail（缺数据就不显示，保持诚实边界）。
    const counts: Record<string, string | undefined> = {
      source: progress.episodes.some((e) => e.hasSourceText) ? `${progress.episodes.length} 集原文` : undefined,
      scenes: progress.sceneCount > 0 ? `${progress.sceneCount} 场` : undefined,
      shots: progress.shotCount > 0 ? `${progress.shotCount} 镜头` : undefined,
      image: progress.shotCount > 0 ? `${progress.imageReadyCount}/${progress.shotCount}` : undefined,
      timeline: hasTimeline ? "已排片" : undefined,
      export: hasFinalVideo ? "成片已就绪" : undefined,
    };
    return stages.map((stage) => ({ ...stage, detail: counts[stage.key] }));
  }, [progress, hasTimeline, hasFinalVideo]);

  const stagePath = (key: string): string => {
    const base = `/projects/${activeProjectId}`;
    const ep = firstEpisodeId;
    switch (key) {
      case "source":
        return `${base}/source`;
      case "scenes":
        return ep ? `${base}/episodes/${ep}/script` : `${base}/script`;
      case "shots":
      case "image":
        return `${base}/storyboard`;
      case "timeline":
      case "export":
        return ep ? `${base}/episodes/${ep}/timeline` : `${base}/timeline`;
      default:
        return base;
    }
  };

  const invalidateProjects = () => void queryClient.invalidateQueries({ queryKey: queryKeys.projects });

  const uploadCover = useMutation({
    mutationFn: (file: File) => {
      if (!activeProject) throw new Error("no active project");
      const body = new FormData();
      body.append("file", file);
      return api.post<Project>(`/projects/${activeProject.id}/cover`, body);
    },
    onSuccess: invalidateProjects,
  });

  const renameProject = useMutation({
    mutationFn: ({ id, revision, name }: { id: string; revision: number; name: string }) => {
      const body: ProjectUpdateRequest = { revision, patch: { name } };
      return api.patch<Project>(`/projects/${id}`, body);
    },
    onSuccess: () => {
      invalidateProjects();
      setRenamingId(null);
    },
  });

  const deleteProject = useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/projects/${id}`),
    onSuccess: () => {
      invalidateProjects();
      if (activeProject && deleteProject.variables === activeProject.id) {
        setActiveId(null); // 重新落到第一个项目
      }
    },
  });

  const startRename = (project: Project) => {
    setRenamingId(project.id);
    setRenameValue(project.name);
  };

  const handleCoverFile = (file: File | undefined | null) => {
    if (file && activeProject) uploadCover.mutate(file);
    if (coverInputRef.current) coverInputRef.current.value = "";
  };

  const confirmDelete = (project: Project) => {
    setMenuOpenId(null);
    if (
      window.confirm(`删除项目《${project.name}》？
其剧集、场景、镜头与角色将一并软删除，不可恢复。`)
    ) {
      deleteProject.mutate(project.id);
    }
  };

  return (
    <div className="project-console">
      <main className="project-home-main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">导演工作台</span>
            <h1>项目</h1>
            <p>
              {filterCount} 个项目{statusFilter !== "all" ? `（${statusLabel[statusFilter] ?? statusFilter}）` : ""} ·
              选择一个项目继续制作
            </p>
          </div>
          <div className="page-filter" ref={filterRef}>
            <button
              type="button"
              className={`icon-button page-filter-btn ${statusFilter !== "all" ? "active" : ""}`}
              aria-label="按状态筛选项目"
              aria-expanded={filterOpen}
              title={statusFilter === "all" ? "筛选项目状态" : `筛选：${statusLabel[statusFilter] ?? statusFilter}`}
              onClick={() => setFilterOpen((v) => !v)}
            >
              <SlidersHorizontal size={19} />
            </button>
            {filterOpen && (
              <div className="filter-menu" role="menu" aria-label="项目状态筛选">
                <button
                  type="button"
                  role="menuitem"
                  className={statusFilter === "all" ? "selected" : ""}
                  onClick={() => {
                    setStatusFilter("all");
                    setFilterOpen(false);
                  }}
                >
                  全部项目 <small>{projects?.length ?? 0}</small>
                </button>
                {(["active", "draft", "completed", "archived"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="menuitem"
                    className={statusFilter === s ? "selected" : ""}
                    onClick={() => {
                      setStatusFilter(s);
                      setFilterOpen(false);
                    }}
                  >
                    {statusLabel[s] ?? s} <small>{(projects ?? []).filter((p) => p.status === s).length}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {isLoading && <div className="home-loading">正在读取项目…</div>}
        {isError && <div className="error-banner">项目读取失败，请确认 Studio Service 已启动。</div>}
        {(uploadCover.error || renameProject.error || deleteProject.error) && (
          <ApiErrorPanel error={uploadCover.error ?? renameProject.error ?? deleteProject.error} />
        )}

        {!isLoading && projects?.length === 0 && (
          <section className="home-empty-card">
            <FolderOpen size={32} />
            <h2>建立第一部漫剧</h2>
            <p>创建项目后导入小说，AI 会把文本拆成场景与镜头。</p>
            <Link to="/projects/new" className="btn primary">
              <Plus size={16} /> 新建项目
            </Link>
          </section>
        )}

        {activeProject && (
          <div className="project-overview-grid">
            <aside className="recent-projects-panel">
              <div className="section-kicker">最近项目</div>
              <div className="recent-project-list">
                {filteredProjects.map((project) => (
                  <div
                    key={project.id}
                    className={`recent-project-wrap ${project.id === activeProject.id ? "active" : ""}`}
                    onClick={() => setActiveId(project.id)}
                  >
                    {renamingId === project.id ? (
                      <div className="recent-project-rename" onClick={(e) => e.stopPropagation()}>
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && renameValue.trim())
                              renameProject.mutate({
                                id: project.id,
                                revision: project.revision,
                                name: renameValue.trim(),
                              });
                            if (e.key === "Escape") setRenamingId(null);
                          }}
                        />
                        <button
                          className="icon-button ok"
                          disabled={!renameValue.trim() || renameProject.isPending}
                          onClick={() =>
                            renameProject.mutate({
                              id: project.id,
                              revision: project.revision,
                              name: renameValue.trim(),
                            })
                          }
                          title="保存名称"
                          aria-label="保存名称"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          className="icon-button"
                          onClick={() => setRenamingId(null)}
                          title="取消"
                          aria-label="取消重命名"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <button type="button" className="recent-project" onClick={() => setActiveId(project.id)}>
                          <span>
                            <strong>《{project.name}》</strong>
                            <small>
                              {project.aspect_ratio ?? "未设置"} · {project.fps ?? 24} FPS ·{" "}
                              {formatShortDate(project.updated_at)}
                            </small>
                          </span>
                          <span className={`project-status status-${project.status}`}>
                            <i /> {statusLabel[project.status] ?? project.status}
                          </span>
                        </button>
                        {/* 编辑/删除是低频危险操作：收入 ··· 菜单，降低误触。 */}
                        <span className="recent-project-actions" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            title="更多操作"
                            aria-haspopup="menu"
                            aria-expanded={menuOpenId === project.id}
                            onClick={() => setMenuOpenId(menuOpenId === project.id ? null : project.id)}
                          >
                            <DotsThree size={16} weight="bold" />
                          </button>
                        </span>
                        {menuOpenId === project.id && (
                          <div className="recent-project-menu" role="menu" ref={menuRef}>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => {
                                setMenuOpenId(null);
                                startRename(project);
                              }}
                            >
                              <PencilSimple size={14} /> 重命名
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              className="danger"
                              disabled={deleteProject.isPending}
                              onClick={() => confirmDelete(project)}
                            >
                              <Trash size={14} /> 删除项目
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
              {projects && projects.length > 0 && filteredProjects.length === 0 && (
                <div className="tree-empty">
                  <p>没有「{statusLabel[statusFilter] ?? statusFilter}」状态的项目</p>
                </div>
              )}
            </aside>

            <section className="project-feature-card">
              <header className="project-head">
                <div className="project-head-text">
                  <div className="project-title-row">
                    <h2>《{activeProject.name}》</h2>
                    <span className={`project-status status-${activeProject.status}`}>
                      {statusLabel[activeProject.status] ?? activeProject.status}
                    </span>
                  </div>
                  <p className="project-description">
                    {activeProject.description ||
                      "从小说到分镜、生成与版本回填，所有制作状态都保存在 Project State。"}
                  </p>
                </div>
                <div className="project-head-actions">
                  <Link to={`/projects/${activeProject.id}/script`} className="btn primary btn-lg">
                    <Play size={16} weight="fill" /> 继续制作
                  </Link>
                </div>
              </header>

              <div className="project-media-row">
                <div className="project-cover-wrap">
                  <img
                    src={activeProject.cover_url ? mediaUrl(activeProject.cover_url) : "/assets/manga-shot.png"}
                    alt={activeProject.cover_url ? `《${activeProject.name}》封面` : "黑白日系写实漫剧镜头"}
                    className={activeProject.cover_url ? "project-cover" : "project-cover cover-default"}
                  />
                  <span className="cover-caption">{activeProject.aspect_ratio ?? "9:16"}</span>
                  <button
                    type="button"
                    className="cover-upload-btn"
                    disabled={uploadCover.isPending}
                    onClick={() => coverInputRef.current?.click()}
                  >
                    <Camera size={15} /> {uploadCover.isPending ? "上传中…" : "更换封面"}
                  </button>
                  <input
                    ref={coverInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp,.gif,image/*"
                    hidden
                    onChange={(event) => handleCoverFile(event.target.files?.[0])}
                  />
                </div>
                <dl className="project-meta-list">
                  <div>
                    <dt>画幅</dt>
                    <dd>{activeProject.aspect_ratio ?? "9:16"}</dd>
                  </div>
                  <div>
                    <dt>帧率</dt>
                    <dd>{activeProject.fps ?? 24} FPS</dd>
                  </div>
                  <div>
                    <dt>最近更新</dt>
                    <dd>{formatDate(activeProject.updated_at)}</dd>
                  </div>
                </dl>
              </div>

              <section className="project-pipeline" aria-label="制作进度">
                <div className="section-kicker">制作进度</div>
                <ol className="proj-stages">
                  {pipeline.map((stage, i) => (
                    <li key={stage.key} className={`proj-stage ${stage.state}`}>
                      <Link to={stagePath(stage.key)} className="proj-stage-link">
                        <span className="proj-stage-dot">
                          {stage.state === "done" ? (
                            <CheckCircle size={15} weight="fill" />
                          ) : (
                            <Circle size={11} weight={stage.state === "running" ? "fill" : "regular"} />
                          )}
                        </span>
                        <span className="proj-stage-index">{String(i + 1).padStart(2, "0")}</span>
                        <span className="proj-stage-label">{stage.label}</span>
                        <span className="proj-stage-detail">
                          {stage.detail ??
                            (stage.state === "done" ? "已完成" : stage.state === "running" ? "进行中" : "等待")}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              </section>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function formatDate(value: string): string {
  return formatDateTime(value);
}

function formatShortDate(value: string): string {
  return formatMonthDay(value);
}
