import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CaretDown,
  CaretLineLeft,
  CaretRight,
  Check,
  FilmStrip,
  FolderOpen,
  ImageSquare,
  MapPin,
  PencilSimple,
  Plus,
  Quotes,
  SlidersHorizontal,
  Sparkle,
  Star,
  Trash,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import { ProjectSettingsModal } from "../settings/ProjectSettingsModal";
import { EntityVersionBlock } from "../libraries/EntityVersionBlock";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type {
  Character,
  CharacterUpdatePatch,
  Episode,
  EpisodeUpdateRequest,
  Location,
  LocationCreate,
  Scene,
  SceneUpdateRequest,
} from "../../api/types";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { canonicalScriptPath, canonicalStoryboardPath, useStudioRoute } from "./studioRoute";

export function ProjectExplorer({ projectId, onCollapse }: { projectId: string; onCollapse: () => void }) {
  const setExplorerCollapsed = useWorkspaceStore((state) => state.setExplorerCollapsed);
  const navigate = useNavigate();
  const route = useStudioRoute();
  const queryClient = useQueryClient();
  // 剧集树的展开/收起是 UI 状态，与选中解耦：再次点击已展开的剧集即可收起。
  const [expandedEpisodeId, setExpandedEpisodeId] = useState<string | null>(null);
  const [renamingEpisodeId, setRenamingEpisodeId] = useState<string | null>(null);
  const [episodeNameValue, setEpisodeNameValue] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const openScript = (episodeId: string) => {
    navigate(canonicalScriptPath(projectId, episodeId));
  };

  const openStoryboard = (sceneId: string, episodeId: string) => {
    navigate(canonicalStoryboardPath(projectId, episodeId, sceneId));
  };

  const toggleEpisode = (episode: Episode) => {
    if (expandedEpisodeId === episode.id) {
      setExpandedEpisodeId(null); // 收起（保持选中，工作区不变）
    } else {
      setExpandedEpisodeId(episode.id); // 展开并选中
      openScript(episode.id);
    }
  };

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>("/projects/" + projectId + "/episodes"),
  });

  const createEpisode = useMutation({
    mutationFn: () =>
      api.post<Episode>("/projects/" + projectId + "/episodes", {
        title: "第 " + ((episodes?.length ?? 0) + 1) + " 集",
      }),
    onSuccess: (episode) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
      openScript(episode.id);
    },
  });

  const createScene = useMutation({
    mutationFn: (episodeId: string) => api.post<Scene>("/episodes/" + episodeId + "/scenes", { name: "新场景" }),
    onSuccess: (scene) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(scene.episode_id) });
      openStoryboard(scene.id, scene.episode_id);
    },
  });

  const renameEpisode = useMutation({
    mutationFn: ({ id, revision, title }: { id: string; revision: number; title: string }) => {
      const body: EpisodeUpdateRequest = { revision, patch: { title } };
      return api.patch<Episode>(`/episodes/${id}`, body);
    },
    onSuccess: (episode) => {
      // refresh local revision from the server response (optimistic concurrency)
      void queryClient.setQueryData<Episode[]>(queryKeys.episodes(projectId), (prev) =>
        (prev ?? []).map((e) =>
          e.id === episode.id
            ? { ...e, title: episode.title, revision: episode.revision, updated_at: episode.updated_at }
            : e,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
      setRenamingEpisodeId(null);
    },
  });

  const deleteEpisode = useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/episodes/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
      if (expandedEpisodeId === deleteEpisode.variables) setExpandedEpisodeId(null);
      // 若被删剧集是当前选中 → 落到第一个剩余剧集
      if (route.episodeId === deleteEpisode.variables) {
        const remaining = (episodes ?? []).filter((e) => e.id !== deleteEpisode.variables);
        if (remaining[0]) openScript(remaining[0].id);
      }
    },
  });

  const startEpisodeRename = (episode: Episode) => {
    setRenamingEpisodeId(episode.id);
    setEpisodeNameValue(episode.title ?? "");
  };

  return (
    <div className="explorer-tree">
      <div className="explorer-head">
        <span>资源树</span>
        <span className="explorer-head-actions">
          <button
            type="button"
            className="icon-button"
            title="项目设置"
            aria-label="项目设置"
            onClick={() => setSettingsOpen(true)}
          >
            <SlidersHorizontal size={15} />
          </button>
          <button
            type="button"
            className="panel-collapse-btn"
            title="收起资源树"
            aria-label="收起资源树"
            onClick={() => {
              setExplorerCollapsed(true);
              onCollapse();
            }}
          >
            <CaretLineLeft size={15} />
          </button>
        </span>
      </div>

      <div className="tree-section">
        <div className="tree-section-title">
          <FolderOpen size={18} weight="fill" /> 制作结构
        </div>
        {!episodes?.length ? (
          <div className="tree-empty">
            <p>还没有剧集</p>
            <button className="text-action" onClick={() => createEpisode.mutate()} disabled={createEpisode.isPending}>
              <Plus size={14} /> 添加剧集
            </button>
          </div>
        ) : (
          episodes.map((episode) => {
            const isOpen = expandedEpisodeId === episode.id;
            return (
              <div key={episode.id} className="tree-item">
                {renamingEpisodeId === episode.id ? (
                  <div className="tree-row-rename" onClick={(e) => e.stopPropagation()}>
                    <input
                      autoFocus
                      value={episodeNameValue}
                      placeholder="剧集名称"
                      onChange={(e) => setEpisodeNameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && episodeNameValue.trim())
                          renameEpisode.mutate({
                            id: episode.id,
                            revision: episode.revision,
                            title: episodeNameValue.trim(),
                          });
                        if (e.key === "Escape") setRenamingEpisodeId(null);
                      }}
                    />
                    <button
                      className="icon-button ok"
                      disabled={!episodeNameValue.trim() || renameEpisode.isPending}
                      onClick={() =>
                        renameEpisode.mutate({
                          id: episode.id,
                          revision: episode.revision,
                          title: episodeNameValue.trim(),
                        })
                      }
                      title="保存名称"
                    >
                      <Check size={14} />
                    </button>
                    <button className="icon-button" onClick={() => setRenamingEpisodeId(null)} title="取消">
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <div className="tree-row-wrap">
                    <button
                      type="button"
                      className={"tree-row episode-row " + (isOpen ? "active" : "")}
                      aria-expanded={isOpen}
                      onClick={() => toggleEpisode(episode)}
                    >
                      {isOpen ? <CaretDown size={14} /> : <CaretRight size={14} />}
                      <FilmStrip size={17} />
                      <span className="tree-label">
                        第 {episode.episode_number} 集 · {episode.title || "未命名"}
                      </span>
                    </button>
                    <span className="tree-row-actions" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        title="重命名剧集"
                        aria-label="重命名剧集"
                        onClick={() => startEpisodeRename(episode)}
                      >
                        <PencilSimple size={13} />
                      </button>
                      <button
                        type="button"
                        className="danger"
                        title="删除剧集"
                        aria-label="删除剧集"
                        disabled={deleteEpisode.isPending}
                        onClick={() => {
                          if (
                            window.confirm(`删除剧集「第 ${episode.episode_number} 集 · ${episode.title || "未命名"}」？
其场景与镜头将一并软删除，不可恢复。`)
                          ) {
                            deleteEpisode.mutate(episode.id);
                          }
                        }}
                      >
                        <Trash size={13} />
                      </button>
                    </span>
                  </div>
                )}
                {isOpen && (
                  <EpisodeScenes
                    episode={episode}
                    projectId={projectId}
                    onCreateScene={() => createScene.mutate(episode.id)}
                  />
                )}
              </div>
            );
          })
        )}
        <button className="tree-add-row" onClick={() => createEpisode.mutate()} disabled={createEpisode.isPending}>
          <Plus size={14} /> 剧集
        </button>
      </div>

      <CharactersSection projectId={projectId} />
      <LocationsSection projectId={projectId} />
      <PromptsSection projectId={projectId} />

      <ProjectSettingsModal projectId={projectId} open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

// Characters block (P1 Character Management + P6-T013 Character Library +
// P6-T014 Set MASTER): library of character cards; each card marks the MASTER
// version and expands into the shared EntityVersionBlock (versions + upload + MASTER).
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard }); // shot cards show names
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
      <div className="tree-section-title">
        <UsersThree size={18} /> 角色 <span className="tree-section-badge">库</span>
      </div>
      {(characters ?? []).map((character) => (
        <CharacterRow
          key={character.id}
          character={character}
          projectId={projectId}
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
      {!characters?.length && !creating && (
        <span className="tree-muted-item">还没有角色 · 手动添加或等 AI 分析建立</span>
      )}

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
          <button
            className="icon-button ok"
            disabled={!newName.trim() || createCharacter.isPending}
            onClick={() => createCharacter.mutate(newName.trim())}
            title="保存"
          >
            <Check size={14} />
          </button>
          <button className="icon-button" onClick={() => setCreating(false)} title="取消">
            <X size={14} />
          </button>
        </div>
      ) : (
        <button className="tree-add-row" onClick={() => setCreating(true)}>
          <Plus size={14} /> 角色
        </button>
      )}
    </div>
  );
}

// Locations block (P6-T015 Location Library): same card + EntityVersionBlock pattern.
function LocationsSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const { data: locations } = useQuery({
    queryKey: queryKeys.locations(projectId),
    queryFn: () => api.get<Location[]>("/projects/" + projectId + "/locations"),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.locations(projectId) });
  };

  const createLocation = useMutation({
    mutationFn: (name: string) => {
      const body: LocationCreate = { name };
      return api.post<Location>("/projects/" + projectId + "/locations", body);
    },
    onSuccess: (location) => {
      invalidate();
      setCreating(false);
      setNewName("");
      setExpandedId(location.id);
    },
  });

  const deleteLocation = useMutation({
    mutationFn: (id: string) => api.delete("/locations/" + id),
    onSuccess: () => {
      invalidate();
      setExpandedId(null);
    },
  });

  return (
    <div className="tree-section quiet-section">
      <div className="tree-section-title">
        <MapPin size={18} /> 地点 <span className="tree-section-badge">库</span>
      </div>
      {(locations ?? []).map((location) => {
        const isOpen = expandedId === location.id;
        return (
          <div key={location.id} className="tree-item">
            <button
              className={"tree-row child " + (isOpen ? "active" : "")}
              onClick={() => setExpandedId(isOpen ? null : location.id)}
            >
              <MapPin size={14} />
              <span className="tree-label">{location.name}</span>
              {location.master_version_id && (
                <span className="badge ok master-badge">
                  <Star size={11} weight="fill" /> MASTER
                </span>
              )}
            </button>
            {isOpen && (
              <div className="char-editor">
                <EntityVersionBlock kind="location" entityId={location.id} projectId={projectId} />
                <div className="char-editor-actions location-delete">
                  <button
                    className="btn danger tiny"
                    disabled={deleteLocation.isPending}
                    onClick={() => {
                      if (window.confirm("删除地点「" + location.name + "」？历史场景引用会保留。"))
                        deleteLocation.mutate(location.id);
                    }}
                  >
                    <Trash size={13} /> 删除
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {!locations?.length && !creating && (
        <span className="tree-muted-item">还没有地点 · 手动添加或等 AI 分析建立</span>
      )}

      {creating ? (
        <div className="char-create-row">
          <input
            autoFocus
            value={newName}
            placeholder="地点名（必填）"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newName.trim()) createLocation.mutate(newName.trim());
              if (e.key === "Escape") setCreating(false);
            }}
          />
          <button
            className="icon-button ok"
            disabled={!newName.trim() || createLocation.isPending}
            onClick={() => createLocation.mutate(newName.trim())}
            title="保存"
          >
            <Check size={14} />
          </button>
          <button className="icon-button" onClick={() => setCreating(false)} title="取消">
            <X size={14} />
          </button>
        </div>
      ) : (
        <button className="tree-add-row" onClick={() => setCreating(true)}>
          <Plus size={14} /> 地点
        </button>
      )}
    </div>
  );
}

// 提示词库（项目级预设，P）：复用 prompts 领域模型（target_type=PROJECT）。
// 每个预设 = 一条 prompt 记录；编辑落成不可变的新版本（vN+1）并自动置为当前。
// 样式与角色/地点库保持一致。
const PROMPT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "SHOT_IMAGE", label: "镜头图" },
  { value: "SHOT_VIDEO", label: "镜头视频" },
  { value: "CHARACTER", label: "角色" },
  { value: "LOCATION", label: "地点" },
  { value: "VOICE", label: "配音" },
  { value: "MUSIC", label: "音乐" },
  { value: "DIRECTOR_INSTRUCTION", label: "导演指令" },
  { value: "CUSTOM", label: "自定义" },
];

interface PromptPreset {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string;
  prompt_type: string;
  active_version_id: string | null;
  versions_count: number;
  active_positive_prompt: string | null;
  active_negative_prompt: string | null;
}

function promptTypeLabel(value: string): string {
  return PROMPT_TYPE_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

function PromptsSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newType, setNewType] = useState("CUSTOM");
  const [newPositive, setNewPositive] = useState("");

  const { data: presets } = useQuery({
    queryKey: queryKeys.projectPrompts(projectId),
    queryFn: () => api.get<PromptPreset[]>("/projects/" + projectId + "/prompts"),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.projectPrompts(projectId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.prompts });
  };

  const createPreset = useMutation({
    mutationFn: () =>
      api.post("/projects/" + projectId + "/prompts", {
        prompt_type: newType,
        positive_prompt: newPositive.trim(),
      }),
    onSuccess: () => {
      invalidate();
      setCreating(false);
      setNewPositive("");
      setNewType("CUSTOM");
      setExpandedId(null);
    },
  });

  return (
    <div className="tree-section quiet-section">
      <div className="tree-section-title">
        <Quotes size={18} /> 提示词 <span className="tree-section-badge">库</span>
      </div>
      {(presets ?? []).map((preset) => (
        <div key={preset.id} className="tree-item">
          <button
            className={"tree-row child " + (expandedId === preset.id ? "active" : "")}
            onClick={() => setExpandedId(expandedId === preset.id ? null : preset.id)}
          >
            <Quotes size={14} />
            <span className="tree-label">
              {promptTypeLabel(preset.prompt_type)}
              {preset.active_positive_prompt ? ` · ${preset.active_positive_prompt}` : " · 空"}
            </span>
            <span className="tree-count">{preset.versions_count}</span>
          </button>
          {expandedId === preset.id && (
            <PromptPresetEditor key={preset.id} preset={preset} onChanged={invalidate} />
          )}
        </div>
      ))}
      {!presets?.length && !creating && (
        <span className="tree-muted-item">还没有提示词预设 · 手动添加</span>
      )}

      {creating ? (
        <div className="char-editor">
          <label className="field">
            <span className="field-label">类型</span>
            <select value={newType} onChange={(e) => setNewType(e.target.value)}>
              {PROMPT_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <textarea
            autoFocus
            rows={2}
            value={newPositive}
            placeholder="提示词内容（必填）"
            onChange={(e) => setNewPositive(e.target.value)}
          />
          <div className="char-editor-actions">
            <button
              className="btn primary tiny"
              disabled={!newPositive.trim() || createPreset.isPending}
              onClick={() => createPreset.mutate()}
            >
              <Check size={13} /> {createPreset.isPending ? "添加中…" : "添加预设"}
            </button>
            <button className="btn secondary tiny" onClick={() => setCreating(false)}>
              <X size={13} /> 取消
            </button>
          </div>
        </div>
      ) : (
        <button className="tree-add-row" onClick={() => setCreating(true)}>
          <Plus size={14} /> 提示词
        </button>
      )}
    </div>
  );
}

function PromptPresetEditor({
  preset,
  onChanged,
}: {
  preset: PromptPreset;
  onChanged: () => void;
}) {
  const [positive, setPositive] = useState(preset.active_positive_prompt ?? "");
  const [negative, setNegative] = useState(preset.active_negative_prompt ?? "");

  const save = useMutation({
    mutationFn: () =>
      api.post(`/prompts/${preset.id}/versions`, { positive_prompt: positive, negative_prompt: negative }),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/prompts/${preset.id}`),
    onSuccess: onChanged,
  });
  const dirty = positive !== (preset.active_positive_prompt ?? "") || negative !== (preset.active_negative_prompt ?? "");

  return (
    <div className="char-editor">
      <label className="field">
        <span className="field-label">正向提示词</span>
        <textarea rows={3} value={positive} onChange={(e) => setPositive(e.target.value)} placeholder="Positive prompt" />
      </label>
      <label className="field">
        <span className="field-label">负向提示词</span>
        <textarea rows={2} value={negative} onChange={(e) => setNegative(e.target.value)} placeholder="Negative prompt（可选）" />
      </label>
      <div className="char-editor-actions">
        <button className="btn primary tiny" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          <Sparkle size={13} /> {save.isPending ? "保存中…" : "保存（新版本）"}
        </button>
        <button
          className="btn danger tiny"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm("删除该提示词预设？其全部版本将一并删除。")) remove.mutate();
          }}
        >
          <Trash size={13} /> 删除
        </button>
      </div>
      <p className="tree-muted-item" style={{ marginTop: 6 }}>
        编辑会生成不可变的 V{preset.versions_count + 1} 并设为当前。
      </p>
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
  projectId,
  expanded,
  onToggle,
  onSave,
  onDelete,
  saving,
}: {
  character: Character;
  projectId: string;
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

  const setField = (key: keyof CharFormFields, value: string) => setForm((f) => ({ ...(f ?? {}), [key]: value }));

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
        <span className="tree-label">
          {character.name}
          {character.alias ? "（" + character.alias + "）" : ""}
        </span>
        {character.master_version_id && (
          <span className="badge ok master-badge">
            <Star size={11} weight="fill" /> MASTER
          </span>
        )}
        <span className="tree-count">{character.shot_count}</span>
        {expanded && <PencilSimple size={13} />}
      </button>
      {expanded && (
        <div className="char-editor">
          <div className="library-section-heading">
            <span className="section-kicker">视觉版本</span>
          </div>
          <EntityVersionBlock kind="character" entityId={character.id} projectId={projectId} />
          <label className="field">
            <span className="field-label">名称</span>
            <input value={active.name} onChange={(e) => setField("name", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">别名</span>
            <input value={active.alias} onChange={(e) => setField("alias", e.target.value)} />
          </label>
          <div className="char-editor-row">
            <label className="field">
              <span className="field-label">性别</span>
              <input value={active.gender} onChange={(e) => setField("gender", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">年龄</span>
              <input value={active.age_description} onChange={(e) => setField("age_description", e.target.value)} />
            </label>
          </div>
          <label className="field">
            <span className="field-label">外貌</span>
            <textarea rows={2} value={active.appearance} onChange={(e) => setField("appearance", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">性格</span>
            <textarea rows={2} value={active.personality} onChange={(e) => setField("personality", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">视觉提示词</span>
            <textarea
              rows={2}
              value={active.visual_prompt}
              placeholder="角色参考 Prompt（生成时稳定形象）"
              onChange={(e) => setField("visual_prompt", e.target.value)}
            />
          </label>
          {conflict && <p className="error-text">{conflict}</p>}
          <div className="char-editor-actions">
            <button className="btn primary tiny" disabled={!dirty || saving} onClick={submit}>
              {saving ? "保存中…" : "保存修改"}
            </button>
            <button className="btn danger tiny" onClick={onDelete} disabled={saving}>
              <Trash size={13} /> 删除
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function EpisodeScenes({
  episode,
  projectId,
  onCreateScene,
}: {
  episode: Episode;
  projectId: string;
  onCreateScene: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const route = useStudioRoute();
  const [renamingSceneId, setRenamingSceneId] = useState<string | null>(null);
  const [sceneNameValue, setSceneNameValue] = useState("");
  const { data: scenes } = useQuery({
    queryKey: queryKeys.scenes(episode.id),
    queryFn: () => api.get<Scene[]>("/episodes/" + episode.id + "/scenes"),
  });

  const openScene = (scene: Scene) => {
    navigate(canonicalStoryboardPath(projectId, scene.episode_id, scene.id));
  };

  const renameScene = useMutation({
    mutationFn: ({ id, revision, name }: { id: string; revision: number; name: string }) => {
      const body: SceneUpdateRequest = { revision, patch: { name } };
      return api.patch<Scene>(`/scenes/${id}`, body);
    },
    onSuccess: (scene) => {
      // refresh local revision from the server response
      void queryClient.setQueryData<Scene[]>(queryKeys.scenes(episode.id), (prev) =>
        (prev ?? []).map((s) =>
          s.id === scene.id ? { ...s, name: scene.name, revision: scene.revision, updated_at: scene.updated_at } : s,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(episode.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      setRenamingSceneId(null);
    },
  });

  const deleteScene = useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/scenes/${id}`),
    onSuccess: (_, sceneId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(episode.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
      // 若删除的是当前打开的 Storyboard 场景 → 返回剧本视图
      if (route.sceneId === sceneId && route.workspace === "storyboard") {
        navigate(canonicalScriptPath(projectId, episode.id));
      }
    },
  });

  const startSceneRename = (scene: Scene) => {
    setRenamingSceneId(scene.id);
    setSceneNameValue(scene.name ?? "");
  };

  return (
    <div className="tree-children">
      {scenes?.map((scene) => (
        <div key={scene.id} className="tree-item">
          {renamingSceneId === scene.id ? (
            <div className="tree-row-rename" onClick={(e) => e.stopPropagation()}>
              <input
                autoFocus
                value={sceneNameValue}
                placeholder="场景名称"
                onChange={(e) => setSceneNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && sceneNameValue.trim())
                    renameScene.mutate({ id: scene.id, revision: scene.revision, name: sceneNameValue.trim() });
                  if (e.key === "Escape") setRenamingSceneId(null);
                }}
              />
              <button
                className="icon-button ok"
                disabled={!sceneNameValue.trim() || renameScene.isPending}
                onClick={() =>
                  renameScene.mutate({ id: scene.id, revision: scene.revision, name: sceneNameValue.trim() })
                }
                title="保存名称"
              >
                <Check size={14} />
              </button>
              <button className="icon-button" onClick={() => setRenamingSceneId(null)} title="取消">
                <X size={14} />
              </button>
            </div>
          ) : (
            <div className="tree-row-wrap">
              <button
                className={"tree-row child " + (route.sceneId === scene.id ? "active" : "")}
                onClick={() => openScene(scene)}
              >
                <ImageSquare size={15} />
                <span className="tree-label">
                  SC{String(scene.scene_number).padStart(2, "0")} · {scene.name ?? "场景"}
                </span>
                <span className="tree-count">{scene.shot_count}</span>
              </button>
              <span className="tree-row-actions" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  title="重命名场景"
                  aria-label="重命名场景"
                  onClick={() => startSceneRename(scene)}
                >
                  <PencilSimple size={13} />
                </button>
                <button
                  type="button"
                  className="danger"
                  title="删除场景"
                  aria-label="删除场景"
                  disabled={deleteScene.isPending}
                  onClick={() => {
                    if (
                      window.confirm(`删除场景「SC${String(scene.scene_number).padStart(2, "0")} · ${scene.name ?? "场景"}」？
其镜头与版本将一并软删除，不可恢复。`)
                    ) {
                      deleteScene.mutate(scene.id);
                    }
                  }}
                >
                  <Trash size={13} />
                </button>
              </span>
            </div>
          )}
        </div>
      ))}
      {!scenes?.length && <span className="tree-muted-item child-note">暂无场景</span>}
      <button className="tree-row child add" onClick={onCreateScene}>
        <Plus size={14} /> 场景
      </button>
    </div>
  );
}
