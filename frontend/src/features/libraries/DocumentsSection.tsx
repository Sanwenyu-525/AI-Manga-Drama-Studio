// 设定文档库区块（database-v0.1 §32.6, api-event-contract §20.1, mvp-spec DOC-005）：
// 项目级源内容归档——人物设定/世界观/大纲/小说原稿等自由文本设定文档。
// Agent 分析按预算注入设定摘要，让角色识别与一致性判断有据可依。
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  FileText,
  PencilSimple,
  Plus,
  Trash,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { SourceDocument, SourceDocumentUpdatePatch } from "../../api/types";
import { DOCUMENT_TYPE_LABELS } from "../../api/types";

type DocFilter = "all" | string;

export function DocumentsSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<DocFilter>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const { data: documents } = useQuery({
    queryKey: queryKeys.documents(projectId),
    queryFn: () => api.get<SourceDocument[]>("/projects/" + projectId + "/documents"),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents(projectId) });
  };

  const createDocument = useMutation({
    mutationFn: (body: { doc_type: string; title: string; content: string }) =>
      api.post<SourceDocument>("/projects/" + projectId + "/documents", body),
    onSuccess: (doc) => {
      invalidate();
      setCreating(false);
      setExpandedId(doc.id);
    },
  });

  const updateDocument = useMutation({
    mutationFn: ({ id, revision, patch }: { id: string; revision: number; patch: SourceDocumentUpdatePatch }) =>
      api.patch<SourceDocument>("/documents/" + id, { revision, patch }),
    onSuccess: () => invalidate(),
  });

  const deleteDocument = useMutation({
    mutationFn: (id: string) => api.delete("/documents/" + id),
    onSuccess: () => {
      invalidate();
      setExpandedId(null);
    },
  });

  const visible = (documents ?? []).filter((doc) => filter === "all" || doc.doc_type === filter);

  return (
    <div className="tree-section quiet-section">
      <div className="document-toolbar">
        <div className="document-filters" role="tablist" aria-label="文档类型筛选">
          <button
            type="button"
            className={`doc-filter-chip ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            全部
          </button>
          {Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => (
            <button
              type="button"
              key={value}
              className={`doc-filter-chip ${filter === value ? "active" : ""}`}
              onClick={() => setFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="tree-add-row document-add"
          onClick={() => setCreating(true)}
        >
          <Plus size={14} /> 设定文档
        </button>
      </div>

      {visible.map((doc) => (
        <DocumentRow
          key={doc.id}
          document={doc}
          projectId={projectId}
          expanded={expandedId === doc.id}
          onToggle={() => setExpandedId(expandedId === doc.id ? null : doc.id)}
          onSave={(patch) => updateDocument.mutate({ id: doc.id, revision: doc.revision, patch })}
          onDelete={() => {
            if (window.confirm(`删除设定文档「${doc.title}」？此操作不可恢复。`)) {
              deleteDocument.mutate(doc.id);
            }
          }}
          saving={updateDocument.isPending}
        />
      ))}
      {!documents?.length && !creating && (
        <span className="tree-muted-item">暂无设定文档。导入人物设定/世界观后，AI 分析会引用它们。</span>
      )}

      {creating && (
        <NewDocumentForm
          onCancel={() => setCreating(false)}
          onSave={(body) => createDocument.mutate(body)}
          saving={createDocument.isPending}
        />
      )}
    </div>
  );
}

interface DocumentFormFields {
  doc_type: string;
  title: string;
  content: string;
  character_id: string;
  location_id: string;
  costume_id: string;
}

function DocumentRow({
  document,
  projectId,
  expanded,
  onToggle,
  onSave,
  onDelete,
  saving,
}: {
  document: SourceDocument;
  projectId: string;
  expanded: boolean;
  onToggle: () => void;
  onSave: (patch: SourceDocumentUpdatePatch) => void;
  onDelete: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<Partial<DocumentFormFields> | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  const active: DocumentFormFields = {
    doc_type: form?.doc_type ?? document.doc_type,
    title: form?.title ?? document.title,
    content: form?.content ?? document.content,
    character_id: form?.character_id ?? document.character_id ?? "",
    location_id: form?.location_id ?? document.location_id ?? "",
    costume_id: form?.costume_id ?? document.costume_id ?? "",
  };

  const setField = (key: keyof DocumentFormFields, value: string) =>
    setForm((f) => ({ ...(f ?? {}), [key]: value }));

  const dirty =
    active.doc_type !== document.doc_type ||
    active.title !== document.title ||
    active.content !== document.content ||
    (active.character_id || "") !== (document.character_id ?? "") ||
    (active.location_id || "") !== (document.location_id ?? "") ||
    (active.costume_id || "") !== (document.costume_id ?? "");

  const submit = () => {
    if (!active.title.trim()) return;
    const patch: SourceDocumentUpdatePatch = {
      doc_type: active.doc_type,
      title: active.title.trim(),
      content: active.content,
      character_id: active.character_id || null,
      location_id: active.location_id || null,
      costume_id: active.costume_id || null,
    };
    try {
      onSave(patch);
    } catch (err) {
      setConflict(err instanceof Error ? err.message : "保存失败");
      return;
    }
    setForm(null);
    setConflict(null);
  };

  return (
    <div className="tree-item">
      <button className="tree-row child" onClick={onToggle}>
        <FileText size={14} />
        <span className="tree-label">
          <span className="badge neutral doc-type-badge">{DOCUMENT_TYPE_LABELS[document.doc_type] ?? document.doc_type}</span>
          {document.title}
        </span>
        {expanded && <PencilSimple size={13} />}
      </button>
      {expanded && (
        <div className="char-editor document-editor">
          <label className="field">
            <span className="field-label">类型</span>
            <select value={active.doc_type} onChange={(e) => setField("doc_type", e.target.value)}>
              {Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">标题</span>
            <input value={active.title} onChange={(e) => setField("title", e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">内容（设定原文）</span>
            <textarea
              rows={6}
              value={active.content}
              placeholder="粘贴人物设定 / 世界观 / 大纲原文。AI 分析时按预算引用这部分内容。"
              onChange={(e) => setField("content", e.target.value)}
            />
          </label>
          <div className="char-editor-row document-links">
            <EntityLinkSelect
              kind="character"
              projectId={projectId}
              value={active.character_id}
              onChange={(v) => setField("character_id", v)}
            />
            <EntityLinkSelect
              kind="location"
              projectId={projectId}
              value={active.location_id}
              onChange={(v) => setField("location_id", v)}
            />
            <EntityLinkSelect
              kind="costume"
              projectId={projectId}
              value={active.costume_id}
              onChange={(v) => setField("costume_id", v)}
            />
          </div>
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

function EntityLinkSelect({
  kind,
  projectId,
  value,
  onChange,
}: {
  kind: "character" | "location" | "costume";
  projectId: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const label = { character: "关联角色", location: "关联地点", costume: "关联服装" }[kind];
  const queryKey =
    kind === "character"
      ? queryKeys.characters(projectId)
      : kind === "location"
        ? queryKeys.locations(projectId)
        : queryKeys.costumes(projectId);
  const { data } = useQuery({
    queryKey,
    queryFn: () =>
      api.get<unknown[]>(`/projects/${projectId}/${kind === "costume" ? "costumes" : kind + "s"}`),
    enabled: Boolean(projectId),
  });
  const items = (data ?? []) as Array<{ id: string; name: string }>;
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">不关联</option>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function NewDocumentForm({
  onCancel,
  onSave,
  saving,
}: {
  onCancel: () => void;
  onSave: (body: { doc_type: string; title: string; content: string }) => void;
  saving: boolean;
}) {
  const [docType, setDocType] = useState("character_setting");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  return (
    <div className="char-editor document-editor">
      <label className="field">
        <span className="field-label">类型</span>
        <select value={docType} onChange={(e) => setDocType(e.target.value)}>
          {Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="field-label">标题</span>
        <input
          autoFocus
          value={title}
          placeholder="如：人物设定·沈亦"
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && title.trim()) onSave({ doc_type: docType, title: title.trim(), content });
            if (e.key === "Escape") onCancel();
          }}
        />
      </label>
      <label className="field">
        <span className="field-label">内容</span>
        <textarea rows={6} value={content} placeholder="设定原文" onChange={(e) => setContent(e.target.value)} />
      </label>
      <div className="char-editor-actions">
        <button
          className="btn primary tiny"
          disabled={!title.trim() || saving}
          onClick={() => onSave({ doc_type: docType, title: title.trim(), content })}
        >
          <Check size={13} /> {saving ? "创建中…" : "创建设定文档"}
        </button>
        <button className="icon-button" onClick={onCancel} title="取消" aria-label="取消创建">
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
