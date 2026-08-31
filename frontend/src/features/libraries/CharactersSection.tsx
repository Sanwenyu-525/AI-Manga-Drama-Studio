// 角色库区块（P1 Character Management + P6-T013 Character Library +
// P6-T014 Set MASTER）：原为资源树「角色」区；资源树移除后由角色页
// （RailWorkspacePages.CharactersWorkspacePage）承载，卡片展开即版本库。
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretRight, Check, FileText, PencilSimple, Plus, Star, Trash, UsersThree, X } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Character, CharacterUpdatePatch, SourceDocument } from "../../api/types";
import { EntityVersionBlock } from "./EntityVersionBlock";

export function CharactersSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // 角色页是本区块的唯一宿主：默认展开列表，避免整页只有一个折叠手柄。
  const [sectionOpen, setSectionOpen] = useState(true);
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
      <button
        type="button"
        className={`tree-section-title ${sectionOpen ? "open" : ""}`}
        onClick={() => setSectionOpen((value) => !value)}
        aria-expanded={sectionOpen}
      >
        <CaretRight size={13} className="tree-section-caret" />
        <UsersThree size={16} /> 角色 <span className="tree-section-count">{characters?.length ?? 0}</span>
      </button>
      {sectionOpen && (
        <>
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
          {!characters?.length && !creating && <span className="tree-muted-item">暂无角色</span>}

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
        </>
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
          <CharacterDocumentsBlock characterId={character.id} projectId={projectId} />
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

// 角色页关联块（database-v0.1 §32.6, mvp-spec DOC-005）：展示该角色名下的人物设定
// 文档（doc_type=character_setting 且 character_id=本角色）。只读摘要 + 跳转知识库。
function CharacterDocumentsBlock({ characterId, projectId }: { characterId: string; projectId: string }) {
  const { data: documents } = useQuery({
    queryKey: queryKeys.documents(projectId),
    queryFn: () => api.get<SourceDocument[]>("/projects/" + projectId + "/documents"),
    enabled: Boolean(projectId),
  });
  const linked = (documents ?? []).filter(
    (doc) => doc.doc_type === "character_setting" && doc.character_id === characterId,
  );
  return (
    <div className="character-documents-block">
      <div className="library-section-heading">
        <span className="section-kicker">关联设定</span>
        <Link className="muted small" to={`/projects/${projectId}/knowledge`} title="打开知识库管理设定文档">
          去知识库
        </Link>
      </div>
      {linked.length === 0 ? (
        <p className="tree-muted-item">
          暂无人物设定文档。在<Link className="muted" to={`/projects/${projectId}/knowledge`}>知识库</Link>
          新建并关联本角色后，AI 分析会引用这些设定。
        </p>
      ) : (
        <ul className="character-document-list">
          {linked.map((doc) => (
            <li key={doc.id}>
              <FileText size={13} />
              <span className="ellipsis">{doc.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
