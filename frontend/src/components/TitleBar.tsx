// Custom window title bar (desktop only, Tauri v2).
//
// tauri.conf.json sets `decorations: false`, so the window has no native title
// bar; this component provides the drag region (data-tauri-drag-region) and the
// Windows-style min/max/close controls. In a plain browser it renders nothing,
// so the web build keeps the browser chrome and pixel-identical layout.
//
// Permissions needed (capabilities/default.json):
//   core:window:allow-start-dragging / allow-minimize / allow-toggle-maximize
//   / allow-close / allow-is-maximized

import { useEffect, useState } from "react";
import { Copy, Minus, Plus, Square, X } from "@phosphor-icons/react";
import { Link, useLocation } from "react-router-dom";
import { getCurrentWindow } from "@tauri-apps/api/window";

const TAURI_RUNTIME = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export function TitleBar() {
  const { pathname } = useLocation();
  const isActive = (path: string) => (path === "/" ? pathname === "/" : pathname.startsWith(path));
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!TAURI_RUNTIME) return;
    document.body.classList.add("tauri");
    let disposed = false;
    let unlisten: (() => void) | undefined;

    void (async () => {
      const win = getCurrentWindow();
      try {
        setMaximized(await win.isMaximized());
      } catch {
        // window API unavailable (e.g. devtools context) — keep default state
      }
      try {
        // Fires on maximize/restore/resize; re-check the flag so the icon stays honest.
        unlisten = await win.onResized(async () => {
          if (disposed) return;
          try {
            setMaximized(await win.isMaximized());
          } catch {
            // ignore transient failures during rapid resizing
          }
        });
      } catch {
        // no permission / event not supported — icon stays at initial state
      }
    })();

    return () => {
      disposed = true;
      document.body.classList.remove("tauri");
      unlisten?.();
    };
  }, []);

  if (!TAURI_RUNTIME) return null;

  const win = getCurrentWindow();
  const toggleMaximize = () => void win.toggleMaximize();
  const minimize = () => void win.minimize();
  const close = () => void win.close();

  return (
    <div className="title-bar">
      <div
        className="title-bar-drag"
        data-tauri-drag-region
        onDoubleClick={toggleMaximize}
        title="双击最大化/还原"
      >
        <img className="title-bar-logo" src="/assets/logo.png" alt="" draggable={false} />
        <span className="title-bar-wordmark" data-tauri-drag-region>
          AI Manga Drama Studio
        </span>
      </div>
      <nav className="title-bar-nav" aria-label="主导航">
        <Link to="/" className={isActive("/") ? "active" : ""} aria-current={isActive("/") ? "page" : undefined}>项目</Link>
        <Link to="/assets" className={isActive("/assets") ? "active" : ""} aria-current={isActive("/assets") ? "page" : undefined}>素材</Link>
        <Link to="/workflows" className={isActive("/workflows") ? "active" : ""} aria-current={isActive("/workflows") ? "page" : undefined}>工作流</Link>
        <Link to="/settings" className={isActive("/settings") ? "active" : ""} aria-current={isActive("/settings") ? "page" : undefined}>设置</Link>
      </nav>
      <div className="title-bar-spacer" data-tauri-drag-region />
      <Link to="/projects/new" className="title-bar-new-project" title="新建项目" draggable={false}>
        <Plus size={13} weight="bold" /> 新建项目
      </Link>
      <div className="title-bar-controls">
        <button type="button" aria-label="最小化" title="最小化" onClick={minimize}>
          <Minus size={15} weight="bold" />
        </button>
        <button type="button" aria-label={maximized ? "还原" : "最大化"} title={maximized ? "还原" : "最大化"} onClick={toggleMaximize}>
          {maximized ? <Copy size={13} weight="bold" /> : <Square size={12} weight="bold" />}
        </button>
        <button type="button" className="close" aria-label="关闭" title="关闭" onClick={close}>
          <X size={15} weight="bold" />
        </button>
      </div>
    </div>
  );
}
