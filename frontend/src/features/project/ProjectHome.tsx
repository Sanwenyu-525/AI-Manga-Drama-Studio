import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Camera, Check, Clock, FolderOpen, PencilSimple, Plus, Play, SlidersHorizontal, Trash, X } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Project, ProjectUpdateRequest } from "../../api/types";

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
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) setFilterOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFilterOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, []);
  const { data: projects, isLoading, isError } = useQuery({
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

  return (
    <div className="project-console">

      <main className="project-home-main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">DIRECTOR'S CONSOLE</span>
            <h1>项目</h1>
            <p>{filterCount} 个项目{statusFilter !== "all" ? `（${statusLabel[statusFilter] ?? statusFilter}）` : ""} · 选择一个项目继续制作</p>
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
                <button type="button" role="menuitem" className={statusFilter === "all" ? "selected" : ""} onClick={() => { setStatusFilter("all"); setFilterOpen(false); }}>
                  全部项目 <small>{projects?.length ?? 0}</small>
                </button>
                {(["active", "draft", "completed", "archived"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="menuitem"
                    className={statusFilter === s ? "selected" : ""}
                    onClick={() => { setStatusFilter(s); setFilterOpen(false); }}
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

        {!isLoading && projects?.length === 0 && (
          <section className="home-empty-card">
            <FolderOpen size={32} />
            <h2>建立第一部漫剧</h2>
            <p>创建项目后导入小说，AI 会把文本拆成场景与镜头。</p>
            <Link to="/projects/new" className="btn primary"><Plus size={16} /> 新建项目</Link>
          </section>
        )}

        {activeProject && (
          <div className="project-overview-grid">
            <aside className="recent-projects-panel">
              <div className="section-kicker">最近项目</div>
              <div className="recent-project-list">
                {filteredProjects.map((project) => (
                  <div key={project.id} className={`recent-project-wrap ${project.id === activeProject.id ? "active" : ""}`} onClick={() => setActiveId(project.id)}>
                    {renamingId === project.id ? (
                      <div className="recent-project-rename" onClick={(e) => e.stopPropagation()}>
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && renameValue.trim()) renameProject.mutate({ id: project.id, revision: project.revision, name: renameValue.trim() });
                            if (e.key === "Escape") setRenamingId(null);
                          }}
                        />
                        <button className="icon-button ok" disabled={!renameValue.trim() || renameProject.isPending} onClick={() => renameProject.mutate({ id: project.id, revision: project.revision, name: renameValue.trim() })} title="保存名称"><Check size={14} /></button>
                        <button className="icon-button" onClick={() => setRenamingId(null)} title="取消"><X size={14} /></button>
                      </div>
                    ) : (
                      <>
                        <button type="button" className="recent-project" onClick={() => setActiveId(project.id)}>
                          <span>
                            <strong>《{project.name}》</strong>
                            <small>{project.aspect_ratio ?? "未设置"} · {project.fps ?? 24} FPS</small>
                          </span>
                          <span className={`project-status status-${project.status}`}>
                            <i /> {statusLabel[project.status] ?? project.status}
                          </span>
                        </button>
                        <span className="recent-project-actions" onClick={(e) => e.stopPropagation()}>
                          <button type="button" title="重命名" onClick={() => startRename(project)}><PencilSimple size={14} /></button>
                          <button
                            type="button"
                            className="danger"
                            title="删除项目"
                            disabled={deleteProject.isPending}
                            onClick={() => {
                              if (window.confirm(`删除项目《${project.name}》？
其剧集、场景、镜头与角色将一并软删除，不可恢复。`)) {
                                deleteProject.mutate(project.id);
                              }
                            }}
                          >
                            <Trash size={14} />
                          </button>
                        </span>
                      </>
                    )}
                  </div>
                ))}
              </div>
              {projects && projects.length > 0 && filteredProjects.length === 0 && (
                <div className="tree-empty"><p>没有「{statusLabel[statusFilter] ?? statusFilter}」状态的项目</p></div>
              )}
              <Link to="/projects/new" className="panel-footer-link"><Plus size={15} /> 新建另一个项目</Link>
            </aside>

            <section className="project-feature-card">
              <div className="project-cover-wrap">
                <img
                  src={activeProject.cover_url ?? "/assets/manga-shot.png"}
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
              <div className="project-feature-content">
                <div className="project-title-row">
                  <h2>《{activeProject.name}》</h2>
                  <span className={`project-status status-${activeProject.status}`}>
                    {statusLabel[activeProject.status] ?? activeProject.status}
                  </span>
                </div>
                <p className="project-description">
                  {activeProject.description || "从小说到分镜、生成与版本回填，所有制作状态都保存在 Project State。"}
                </p>

                <div className="project-facts">
                  <div><span>画幅</span><strong>{activeProject.aspect_ratio ?? "9:16"}</strong></div>
                  <div><span>帧率</span><strong>{activeProject.fps ?? 24} FPS</strong></div>
                  <div><span>状态</span><strong>{statusLabel[activeProject.status] ?? activeProject.status}</strong></div>
                  <div><span>最近更新</span><strong>{formatDate(activeProject.updated_at)}</strong></div>
                </div>

                <div className="project-actions">
                  {/* One entry point into the studio; the URL opens the script view
                      where the user continues toward scenes/storyboard. */}
                  <Link to={`/projects/${activeProject.id}/script`} className="btn primary">
                    <Play size={16} weight="fill" /> 打开工作台
                  </Link>
                  <span className="muted small"><ArrowRight size={14} /> 剧本 → 场景 → 分镜</span>
                </div>

                <div className="recent-activity">
                  <div className="section-kicker">制作流程</div>
                  <div className="activity-row"><Clock size={16} /><span>剧本 → 场景 → 分镜 → 生成 → 版本</span><small>Project State</small></div>
                </div>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}
