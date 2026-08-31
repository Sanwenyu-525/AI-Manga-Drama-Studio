// DirectoryBrowserModal (P-LocalModels): server-backed directory picker for the
// settings page path inputs. The Studio backend lists the local filesystem
// (GET /providers/fs/list), so the same picker works in both the browser (dev)
// and the Tauri shell — a web page cannot get absolute paths from a native
// folder dialog. Empty path = root view (Windows drives / POSIX /). Click a
// directory to enter it; 「选择此目录」 confirms the currently browsed directory.

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CaretRight, Check, File, Folder, FolderOpen, House, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { formatBytes } from "../../lib/format";

// GET /providers/fs/list：{path, parent, entries, truncated, error?}。
export interface FsEntry {
  name: string;
  path: string;
  type: "dir" | "file";
  size_bytes?: number;
}

interface FsListing {
  path: string;
  parent: string | null;
  entries: FsEntry[];
  truncated: boolean;
  error?: string;
}

interface DirectoryBrowserModalProps {
  open: boolean;
  title: string;
  /** 打开时初始浏览的目录（空串 = 根视图）；路径失效时自动回落根视图。 */
  initialPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function DirectoryBrowserModal({ open, title, initialPath, onSelect, onClose }: DirectoryBrowserModalProps) {
  // cwd = "" 表示根视图（盘符列表）。跳转/进入子目录都走 goto 统一同步 cwd 与地址草稿。
  const [cwd, setCwd] = useState("");
  const [pathDraft, setPathDraft] = useState("");
  const [fallbackNote, setFallbackNote] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      const initial = initialPath.trim();
      setCwd(initial);
      setPathDraft(initial);
      setFallbackNote(null);
    }
  }, [open, initialPath]);

  const listing = useQuery({
    queryKey: ["fs-list", cwd],
    queryFn: () => api.get<FsListing>(`/providers/fs/list?path=${encodeURIComponent(cwd)}`),
    enabled: open,
    retry: 0,
    staleTime: 5_000,
  });

  // 初始路径失效（不存在/无权限）→ 自动回根视图，弹窗不至于卡死在错误态。
  useEffect(() => {
    if (listing.isError && cwd !== "") {
      setFallbackNote(`无法打开 ${cwd}（不存在或不可访问），已回到根目录。`);
      setCwd("");
      setPathDraft("");
    }
  }, [listing.isError, cwd]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const goto = (path: string) => {
    setFallbackNote(null);
    setCwd(path);
    setPathDraft(path);
  };

  const entries = listing.data?.entries ?? [];
  const atRoot = cwd === "";
  const selectDisabled = atRoot || listing.isPending || !!listing.data?.error;

  return (
    <div
      className="settings-modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="settings-modal fs-browser" role="dialog" aria-modal="true" aria-label={title}>
        <header className="settings-modal-head">
          <div>
            <span className="eyebrow">选择目录</span>
            <h2>
              <FolderOpen size={18} /> {title}
            </h2>
          </div>
          <button type="button" className="icon-button" aria-label="关闭目录浏览" onClick={onClose}>
            <X size={17} />
          </button>
        </header>

        <div className="settings-modal-body fs-browser-body">
          <div className="fs-browser-toolbar">
            <button
              type="button"
              className="btn secondary compact"
              disabled={!listing.data?.parent}
              onClick={() => listing.data?.parent && goto(listing.data.parent)}
              title="返回上一级目录"
            >
              <ArrowLeft size={13} /> 上一级
            </button>
            <button
              type="button"
              className="btn secondary compact"
              onClick={() => goto("")}
              title="回到盘符 / 根目录列表"
            >
              <House size={13} /> 根目录
            </button>
            <div className="fs-path-jump">
              <input
                value={pathDraft}
                placeholder="输入完整目录路径后回车"
                onChange={(e) => setPathDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") goto(pathDraft.trim());
                }}
                aria-label="目录路径"
              />
              <button type="button" className="btn secondary compact" onClick={() => goto(pathDraft.trim())}>
                跳转
              </button>
            </div>
          </div>

          {fallbackNote && <p className="muted small">{fallbackNote}</p>}
          {listing.isPending && <p className="muted small">正在读取目录…</p>}
          {listing.data?.error && <p className="test-result fail">{listing.data.error}</p>}
          {!listing.isPending && !listing.data?.error && entries.length === 0 && (
            <p className="muted small">此目录为空。</p>
          )}
          {listing.data?.truncated && <p className="muted small">条目过多，仅显示前 {entries.length} 项。</p>}

          <ul className="fs-entry-list">
            {entries.map((entry) =>
              entry.type === "dir" ? (
                <li key={entry.path}>
                  <button type="button" className="fs-entry" onClick={() => goto(entry.path)} title={entry.path}>
                    <Folder size={15} weight="fill" />
                    <span className="fs-entry-name">{entry.name}</span>
                    <CaretRight size={12} className="fs-entry-go" />
                  </button>
                </li>
              ) : (
                <li key={entry.path}>
                  <span className="fs-entry is-file" title={`${entry.path}（仅支持选择目录）`}>
                    <File size={15} />
                    <span className="fs-entry-name">{entry.name}</span>
                    <span className="muted small mono">{formatBytes(entry.size_bytes ?? 0)}</span>
                  </span>
                </li>
              ),
            )}
          </ul>
        </div>

        <footer className="fs-browser-actions">
          <span className="muted small mono fs-cwd">{listing.data?.path || "根目录（本机盘符）"}</span>
          <button type="button" className="btn secondary" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={selectDisabled}
            onClick={() => onSelect(cwd)}
            title="把当前浏览的目录填入路径输入框"
          >
            <Check size={15} /> 选择此目录
          </button>
        </footer>
      </div>
    </div>
  );
}
