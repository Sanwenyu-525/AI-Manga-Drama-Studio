import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Scene } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";

// Project → Episode → Scene tree (frontend-ux §5-6). Clicking a scene opens the storyboard.
export function ProjectExplorer({ projectId }: { projectId: string }) {
  const selection = useSelectionStore((s) => s.selection);
  const setEpisode = useSelectionStore((s) => s.setEpisode);
  const setScene = useSelectionStore((s) => s.setScene);
  const queryClient = useQueryClient();

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>(`/projects/${projectId}/episodes`),
  });

  const createEpisode = useMutation({
    mutationFn: () => api.post<Episode>(`/projects/${projectId}/episodes`, { title: `Episode ${(episodes?.length ?? 0) + 1}` }),
    onSuccess: (episode) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
      setEpisode(episode.id);
    },
  });

  const createScene = useMutation({
    mutationFn: (episodeId: string) =>
      api.post<Scene>(`/episodes/${episodeId}/scenes`, { name: `场景 ${(episodes?.length ?? 0) + 1}` }),
    onSuccess: (scene) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(scene.episode_id) });
      setScene(scene.id);
    },
  });

  return (
    <div className="explorer-tree">
      <div className="explorer-head">
        <span>PROJECT</span>
        <button className="btn tiny" onClick={() => createEpisode.mutate()} disabled={createEpisode.isPending} title="添加剧集">
          + 剧集
        </button>
      </div>

      {!episodes || episodes.length === 0 ? (
        <p className="muted small">还没有剧集</p>
      ) : (
        episodes.map((episode) => {
          const isOpen = selection.episodeId === episode.id;
          return (
            <div key={episode.id} className="tree-item">
              <button
                className={`tree-row ${isOpen ? "active" : ""}`}
                onClick={() => setEpisode(episode.id)}
              >
                <span className="tree-caret">{isOpen ? "▼" : "▶"}</span>
                <span className="tree-label">EP{String(episode.episode_number).padStart(2, "0")} {episode.title}</span>
              </button>
              {isOpen && <EpisodeScenes episode={episode} onCreateScene={() => createScene.mutate(episode.id)} />}
            </div>
          );
        })
      )}
    </div>
  );
}

function EpisodeScenes({ episode, onCreateScene }: { episode: Episode; onCreateScene: () => void }) {
  const selection = useSelectionStore((s) => s.selection);
  const setScene = useSelectionStore((s) => s.setScene);

  const { data: scenes } = useQuery({
    queryKey: queryKeys.scenes(episode.id),
    queryFn: () => api.get<Scene[]>(`/episodes/${episode.id}/scenes`),
  });

  return (
    <div className="tree-children">
      {!scenes || scenes.length === 0 ? (
        <p className="muted small indent">暂无场景</p>
      ) : (
        scenes.map((scene) => (
          <button
            key={scene.id}
            className={`tree-row child ${selection.sceneId === scene.id ? "active" : ""}`}
            onClick={() => setScene(scene.id)}
          >
            <span className="tree-label">SC{String(scene.scene_number).padStart(2, "0")} {scene.name ?? ""}</span>
            <span className="tree-count">{scene.shot_count} 镜</span>
          </button>
        ))
      )}
      <button className="tree-row child add" onClick={onCreateScene}>
        + 场景
      </button>
    </div>
  );
}
