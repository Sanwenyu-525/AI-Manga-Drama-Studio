import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretDown, CaretRight, FilmStrip, FolderOpen, FunnelSimple, ImageSquare, MapPin, Plus, UsersThree } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Scene } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";

export function ProjectExplorer({ projectId }: { projectId: string }) {
  const selection = useSelectionStore((state) => state.selection);
  const setEpisode = useSelectionStore((state) => state.setEpisode);
  const setScene = useSelectionStore((state) => state.setScene);
  const queryClient = useQueryClient();

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>(`/projects/${projectId}/episodes`),
  });

  const createEpisode = useMutation({
    mutationFn: () => api.post<Episode>(`/projects/${projectId}/episodes`, { title: `第 ${(episodes?.length ?? 0) + 1} 集` }),
    onSuccess: (episode) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
      setEpisode(episode.id);
    },
  });

  const createScene = useMutation({
    mutationFn: (episodeId: string) => api.post<Scene>(`/episodes/${episodeId}/scenes`, { name: "新场景" }),
    onSuccess: (scene) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(scene.episode_id) });
      setScene(scene.id);
    },
  });

  return (
    <div className="explorer-tree">
      <div className="explorer-head">
        <span>资源树</span>
        <FunnelSimple size={16} />
      </div>

      <div className="tree-section">
        <div className="tree-section-title"><FolderOpen size={18} weight="fill" /> 制作结构</div>
        {!episodes?.length ? (
          <div className="tree-empty">
            <p>还没有剧集</p>
            <button className="text-action" onClick={() => createEpisode.mutate()} disabled={createEpisode.isPending}><Plus size={14} /> 添加剧集</button>
          </div>
        ) : (
          episodes.map((episode) => {
            const isOpen = selection.episodeId === episode.id;
            return (
              <div key={episode.id} className="tree-item">
                <button className={`tree-row episode-row ${isOpen ? "active" : ""}`} onClick={() => setEpisode(episode.id)}>
                  {isOpen ? <CaretDown size={14} /> : <CaretRight size={14} />}
                  <FilmStrip size={17} />
                  <span className="tree-label">第 {episode.episode_number} 集 · {episode.title || "未命名"}</span>
                </button>
                {isOpen && <EpisodeScenes episode={episode} onCreateScene={() => createScene.mutate(episode.id)} />}
              </div>
            );
          })
        )}
        <button className="tree-add-row" onClick={() => createEpisode.mutate()} disabled={createEpisode.isPending}><Plus size={14} /> 剧集</button>
      </div>

      <div className="tree-section quiet-section">
        <div className="tree-section-title"><UsersThree size={18} /> 角色</div>
        <span className="tree-muted-item">随 AI 分析结果建立</span>
      </div>
      <div className="tree-section quiet-section">
        <div className="tree-section-title"><MapPin size={18} /> 场景资产</div>
        <span className="tree-muted-item">镜头生成后自动归档</span>
      </div>
    </div>
  );
}

function EpisodeScenes({ episode, onCreateScene }: { episode: Episode; onCreateScene: () => void }) {
  const selection = useSelectionStore((state) => state.selection);
  const setScene = useSelectionStore((state) => state.setScene);
  const { data: scenes } = useQuery({
    queryKey: queryKeys.scenes(episode.id),
    queryFn: () => api.get<Scene[]>(`/episodes/${episode.id}/scenes`),
  });

  return (
    <div className="tree-children">
      {scenes?.map((scene) => (
        <button key={scene.id} className={`tree-row child ${selection.sceneId === scene.id ? "active" : ""}`} onClick={() => setScene(scene.id)}>
          <ImageSquare size={15} />
          <span className="tree-label">SC{String(scene.scene_number).padStart(2, "0")} · {scene.name ?? "场景"}</span>
          <span className="tree-count">{scene.shot_count}</span>
        </button>
      ))}
      {!scenes?.length && <span className="tree-muted-item child-note">暂无场景</span>}
      <button className="tree-row child add" onClick={onCreateScene}><Plus size={14} /> 场景</button>
    </div>
  );
}
