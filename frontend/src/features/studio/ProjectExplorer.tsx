import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretDown, CaretRight, Check, FilmStrip, FolderOpen, FunnelSimple, ImageSquare, MapPin, PencilSimple, Plus, Trash, UsersThree, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Character, CharacterUpdatePatch, Episode, Scene } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";

export function ProjectExplorer({ projectId }: { projectId: string }) {
  const selection = useSelectionStore((state) => state.selection);
  const setEpisode = useSelectionStore((state) => state.setEpisode);
  const setScene = useSelectionStore((state) => state.setScene);
  const queryClient = useQueryClient();

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>("/projects/" + projectId + "/episodes"),
  });

  const createEpisode = useMutation({
    mutationFn: () => api.post<Episode>("/projects/" + projectId + "/episodes", { title: "第 " + ((episodes?.length ?? 0) + 1) + " 集" }),
    onSuccess: (episode) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
      setEpisode(episode.id);
    },
  });

  const createScene = useMutation({
    mutationFn: (episodeId: string) => api.post<Scene>("/episodes/" + episodeId + "/scenes", { name: "新场景" }),
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
                <button className={"tree-row episode-row " + (isOpen ? "active" : "")} onClick={() => setEpisode(episode.id)}>
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

      <CharactersSection projectId={projectId} />

      <div className="tree-section quiet-section">
        <div className="tree-section-title"><MapPin size={18} /> 场景资产</div>
        <span className="tree-muted-item">镜头生成后自动归档</span>
      </div>
    </div>
  );
}

// Characters block (P1 Character Management, frontend-ux §219): list + inline create/edit/delete.
function CharactersSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const { data: characters } = useQuery({
    queryKey: queryKeys.characters(projectId),
    queryFn: () => api.get<Character[]>("/projects/" + projectId + "/characters"),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });
  };

  const createCharacter = useMutation({
    mutationFn: (name: string) => api.post<Character>("/projects/" + projectId + "/characters", { name }),
    onSuccess: (character) => {
      invalidate();
      setCreating(false);
      setNewName("");
      setExpandedId(character.id);
    },
  });

  const updateCharacter = useMutation({
    mutationFn: ({ id, revision, patch }: { id: string; revision: number; patch: CharacterUpdatePatch }) =>
      api.patch<Character>("/characters/" + id, { revision, patch }),
    onSuccess: () => {
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ["storyboard"] }); // shot cards show names
    },
  });

  const deleteCharacter = useMutation({
    mutationFn: (id: string) => api.delete("/characters/" + id),
    onSuccess: () => {
      invalidate();
      setExpandedId(null);
    },
  });

  return (
    <div className="tree-section quiet-section">
      <div className="tree-section-title"><UsersThree size={18} /> 角色</div>
      {(characters ?? []).map((character) => (
        <CharacterRow
          key={character.id}
          character={character}
          expanded={expandedId === character.id}
          onToggle={() => setExpandedId(expandedId === character.id ? null : character.id)}
          onSave={(patch) => updateCharacter.mutate({ id: character.id, revision: character.revision, patch })}
          onDelete={() => {
            if (window.confirm("删除角色「" + character.name + "」？历史镜头引用会保留，但不再出现在角色列表。")) {
              deleteCharacter.mutate(character.id);
            }
          }}
          saving={updateCharacter.isPending}
        />
      ))}
      {!characters?.length && !creating && <span className="tree-muted-item">还没有角色 · 手动添加或等 AI 分析建立</span>}

      {creating ? (
        <div className="char-create-row">
          <input
            autoFocus
            value={newName}
            placeholder="角色名（必填）"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newName.trim()) createCharacter.mutate(newName.trim());
              if (e.key === "Escape") setCreating(false);
            }}
          />
          <button className="icon-button ok" disabled={!newName.trim() || createCharacter.isPending} onClick={() => createCharacter.mutate(newName.trim())} title="保存">
            <Check size={14} />
          </button>
          <button className="icon-button" onClick={() => setCreating(false)} title="取消"><X size={14} /></button>
        </div>
      ) : (
        <button className="tree-add-row" onClick={() => setCreating(true)}><Plus size={14} /> 角色</button>
      )}
    </div>
  );
}

interface CharFormFields {
  name: string;
  alias: string;
  gender: string;
  age_description: string;
  appearance: string;
  personality: string;
  visual_prompt: string;
}

function CharacterRow({
  character,
  expanded,
  onToggle,
  onSave,
  onDelete,
  saving,
}: {
  character: Character;
  expanded: boolean;
  onToggle: () => void;
  onSave: (patch: CharacterUpdatePatch) => void;
  onDelete: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<Partial<CharFormFields> | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  const active: CharFormFields = {
    name: form?.name ?? character.name,
    alias: form?.alias ?? character.alias ?? "",
    gender: form?.gender ?? character.gender ?? "",
    age_description: form?.age_description ?? character.age_description ?? "",
    appearance: form?.appearance ?? character.appearance ?? "",
    personality: form?.personality ?? character.personality ?? "",
    visual_prompt: form?.visual_prompt ?? character.visual_prompt ?? "",
  };

  const setField = (key: keyof CharFormFields, value: string) =>
    setForm((f) => ({ ...(f ?? {}), [key]: value }));

  const dirty =
    active.name !== character.name ||
    active.alias !== (character.alias ?? "") ||
    active.gender !== (character.gender ?? "") ||
    active.age_description !== (character.age_description ?? "") ||
    active.appearance !== (character.appearance ?? "") ||
    active.personality !== (character.personality ?? "") ||
    active.visual_prompt !== (character.visual_prompt ?? "");

  const submit = () => {
    if (!active.name.trim()) return;
    const patch: CharacterUpdatePatch = {
      name: active.name.trim(),
      alias: active.alias || null,
      gender: active.gender || null,
      age_description: active.age_description || null,
      appearance: active.appearance || null,
      personality: active.personality || null,
      visual_prompt: active.visual_prompt || null,
    };
    onSave(patch);
    setForm(null);
    setConflict(null);
  };

  return (
    <div className="tree-item">
      <button className="tree-row child" onClick={onToggle}>
        <UsersThree size={14} />
        <span className="tree-label">{character.name}{character.alias ? "（" + character.alias + "）" : ""}</span>
        <span className="tree-count">{character.shot_count}</span>
        {expanded && <PencilSimple size={13} />}
      </button>
      {expanded && (
        <div className="char-editor">
          <label className="field"><span className="field-label">名称</span>
            <input value={active.name} onChange={(e) => setField("name", e.target.value)} />
          </label>
          <label className="field"><span className="field-label">别名</span>
            <input value={active.alias} onChange={(e) => setField("alias", e.target.value)} />
          </label>
          <div className="char-editor-row">
            <label className="field"><span className="field-label">性别</span>
              <input value={active.gender} onChange={(e) => setField("gender", e.target.value)} />
            </label>
            <label className="field"><span className="field-label">年龄</span>
              <input value={active.age_description} onChange={(e) => setField("age_description", e.target.value)} />
            </label>
          </div>
          <label className="field"><span className="field-label">外貌</span>
            <textarea rows={2} value={active.appearance} onChange={(e) => setField("appearance", e.target.value)} />
          </label>
          <label className="field"><span className="field-label">性格</span>
            <textarea rows={2} value={active.personality} onChange={(e) => setField("personality", e.target.value)} />
          </label>
          <label className="field"><span className="field-label">视觉提示词</span>
            <textarea rows={2} value={active.visual_prompt} placeholder="角色参考 Prompt（生成时稳定形象）" onChange={(e) => setField("visual_prompt", e.target.value)} />
          </label>
          {conflict && <p className="error-text">{conflict}</p>}
          <div className="char-editor-actions">
            <button className="btn primary tiny" disabled={!dirty || saving} onClick={submit}>
              {saving ? "保存中…" : "保存修改"}
            </button>
            <button className="btn danger tiny" onClick={onDelete} disabled={saving}><Trash size={13} /> 删除</button>
          </div>
        </div>
      )}
    </div>
  );
}

function EpisodeScenes({ episode, onCreateScene }: { episode: Episode; onCreateScene: () => void }) {
  const selection = useSelectionStore((state) => state.selection);
  const setScene = useSelectionStore((state) => state.setScene);
  const { data: scenes } = useQuery({
    queryKey: queryKeys.scenes(episode.id),
    queryFn: () => api.get<Scene[]>("/episodes/" + episode.id + "/scenes"),
  });

  return (
    <div className="tree-children">
      {scenes?.map((scene) => (
        <button key={scene.id} className={"tree-row child " + (selection.sceneId === scene.id ? "active" : "")} onClick={() => setScene(scene.id)}>
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
