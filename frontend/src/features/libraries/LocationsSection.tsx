// 地点库区块（自主迭代 03 — 场景一致性闭环）：管理项目场景地点的设定、视觉
// 提示词与参考资产版本链（MASTER）。镜像 CharactersSection 结构；视觉版本由
// EntityVersionBlock(kind="location") 承载（后端 LocationService 早已落地，
// 本轮补上前端生产入口）。场景绑定地点后，镜头生成自动注入地点 MASTER 参考图，
// 实现同一场景的画面环境稳定。
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretRight, Check, FileText, MapPin, PencilSimple, Plus, Star, Trash, X } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Location, LocationUpdatePatch, SourceDocument } from "../../api/types";
import { EntityVersionBlock } from "./EntityVersionBlock";

export function LocationsSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [sectionOpen, setSectionOpen] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const { data: locations } = useQuery({
    queryKey: queryKeys.locations(projectId),
    queryFn: () => api.get<Location[]>("/projects/" + projectId + "/locations"),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.locations(projectId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes }); // scene 头部展示地点名
  };

  const createLocation = useMutation({
    mutationFn: (name: string) => api.post<Location>("/projects/" + projectId + "/locations", { name }),
    onSuccess: (location) => {
      invalidate();
      setCreating(false);
      setNewName("");
      setExpandedId(location.id);
    },
  });

  const updateLocation = useMutation({
    mutationFn: ({ id, revision, patch }: { id: string; revision: number; patch: LocationUpdatePatch }) =>
      api.patch<Location>("/locations/" + id, { revision, patch }),
    onSuccess: () => {
      invalidate();
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard }); // scene meta line 显示地点名
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
      <button
        type="button"
        className={`tree-section-title ${sectionOpen ? "open" : ""}`}
        onClick={() => setSectionOpen((value) => !value)}
        aria-expanded={sectionOpen}
      >
        <CaretRight size={13} className="tree-section-caret" />
        <MapPin size={16} /> 地点 <span className="tree-section-count">{locations?.length ?? 0}</span>
      </button>
      {sectionOpen && (
        <>
          {(locations ?? []).map((location) => (
            <LocationRow
              key={location.id}
              location={location}
              projectId={projectId}
              expanded={expandedId === location.id}
              onToggle={() => setExpandedId(expandedId === location.id ? null : location.id)}
              onSave={(patch) => updateLocation.mutate({ id: location.id, revision: location.revision, patch })}
              onDelete={() => {
                if (window.confirm(`删除地点「${location.name}」？已绑定的场景会保留引用，但地点不再出现在列表。`)) {
                  deleteLocation.mutate(location.id);
                }
              }}
              saving={updateLocation.isPending}
            />
          ))}
          {!locations?.length && !creating && <span className="tree-muted-item">暂无地点</span>}

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
                aria-label="保存地点"
              >
                <Check size={14} />
              </button>
              <button className="icon-button" onClick={() => setCreating(false)} title="取消" aria-label="取消创建">
                <X size={14} />
              </button>
            </div>
          ) : (
            <button className="tree-add-row" onClick={() => setCreating(true)}>
              <Plus size={14} /> 地点
            </button>
          )}
        </>
      )}
    </div>
  );
}

interface LocFormFields {
  name: string;
  description: string;
  visual_prompt: string;
}

function LocationRow({
  location,
  projectId,
  expanded,
  onToggle,
  onSave,
  onDelete,
  saving,
}: {
  location: Location;
  projectId: string;
  expanded: boolean;
  onToggle: () => void;
  onSave: (patch: LocationUpdatePatch) => void;
  onDelete: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<Partial<LocFormFields> | null>(null);

  const active: LocFormFields = {
    name: form?.name ?? location.name,
    description: form?.description ?? location.description ?? "",
    visual_prompt: form?.visual_prompt ?? location.visual_prompt ?? "",
  };

  const setField = (key: keyof LocFormFields, value: string) => setForm((f) => ({ ...(f ?? {}), [key]: value }));

  const dirty =
    active.name !== location.name ||
    active.description !== (location.description ?? "") ||
    active.visual_prompt !== (location.visual_prompt ?? "");

  const submit = () => {
    if (!active.name.trim()) return;
    const patch: LocationUpdatePatch = {
      name: active.name.trim(),
      description: active.description || null,
      visual_prompt: active.visual_prompt || null,
    };
    onSave(patch);
    setForm(null);
  };

  return (
    <div className="tree-item">
      <button className="tree-row child" onClick={onToggle}>
        <MapPin size={14} />
        <span className="tree-label">{location.name}</span>
        {location.master_version_id && (
          <span className="badge ok master-badge">
            <Star size={11} weight="fill" /> MASTER
          </span>
        )}
        {expanded && <PencilSimple size={13} />}
      </button>
      {expanded && (
        <div className="char-editor">
          <div className="library-section-heading">
            <span className="section-kicker">视觉版本</span>
          </div>
          <EntityVersionBlock kind="location" entityId={location.id} projectId={projectId} />
          <LocationDocumentsBlock locationId={location.id} projectId={projectId} />
          <label className="field">
            <span className="field-label">名称</span>
            <input value={active.name} onChange={(e) => setField("name", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">描述</span>
            <textarea rows={2} value={active.description} onChange={(e) => setField("description", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">视觉提示词</span>
            <textarea
              rows={2}
              value={active.visual_prompt}
              placeholder="地点参考 Prompt（生成时稳定环境）"
              onChange={(e) => setField("visual_prompt", e.target.value)}
            />
          </label>
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

// 地点关联设定文档（世界观/场景设定，location_id=本地点）。只读摘要 + 跳转知识库。
function LocationDocumentsBlock({ locationId, projectId }: { locationId: string; projectId: string }) {
  const { data: documents } = useQuery({
    queryKey: queryKeys.documents(projectId),
    queryFn: () => api.get<SourceDocument[]>("/projects/" + projectId + "/documents"),
    enabled: Boolean(projectId),
  });
  const linked = (documents ?? []).filter((doc) => doc.location_id === locationId);
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
          暂无场景设定文档。在<Link className="muted" to={`/projects/${projectId}/knowledge`}>知识库</Link>
          新建并关联本地点后，AI 分析会引用这些设定。
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
