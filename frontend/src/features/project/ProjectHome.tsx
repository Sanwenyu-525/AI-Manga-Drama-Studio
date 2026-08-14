import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Project } from "../../api/types";

export function ProjectHome() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: projects, isLoading } = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<Project[]>("/projects"),
  });

  const createProject = useMutation({
    mutationFn: (name: string) =>
      api.post<Project>("/projects", { name, aspect_ratio: "9:16", fps: 24 }),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      navigate(`/projects/${project.id}`);
    },
  });

  const handleCreate = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (name) createProject.mutate(name);
  };

  return (
    <div className="home">
      <header className="home-header">
        <h1>AI Manga Drama Studio</h1>
        <p className="muted">AI 原生漫剧制作工作台 — MVP</p>
      </header>

      <section className="home-card">
        <h2>新建项目</h2>
        <form onSubmit={handleCreate} className="row gap">
          <input name="name" placeholder="项目名称，如：《最后一种打法》" required className="input grow" />
          <button type="submit" className="btn primary" disabled={createProject.isPending}>
            {createProject.isPending ? "创建中…" : "创建"}
          </button>
        </form>
        {createProject.isError && <p className="error-text">创建失败：{String(createProject.error)}</p>}
      </section>

      <section className="home-card">
        <h2>项目</h2>
        {isLoading && <p className="muted">加载中…</p>}
        {projects?.length === 0 && <p className="muted">还没有项目，先创建一个。</p>}
        <ul className="project-list">
          {projects?.map((project) => (
            <li key={project.id}>
              <Link to={`/projects/${project.id}`} className="project-row">
                <span className="project-name">{project.name}</span>
                <span className="muted">
                  {project.aspect_ratio ?? "—"} · {project.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
