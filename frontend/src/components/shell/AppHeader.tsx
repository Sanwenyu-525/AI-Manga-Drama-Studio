// Global Application Header — 52px (DESIGN.md §4 / P0 frozen shell).
//
// Left: DeepSeek Harness brand; Center: level-1 mode switch [ Harness | 漫剧智能体 ];
// Right: 新建项目 entry + (Tauri only) the Windows-style window controls. The whole
// non-interactive area is the drag region, so the old standalone 36px TitleBar is
// replaced by this header in the desktop build.
//
// Permissions needed (capabilities/default.json): core:window:allow-start-dragging /
// allow-minimize / allow-toggle-maximize / allow-close / allow-is-maximized.

import { useEffect, useState } from "react";
import { Copy, Minus, Plus, Square, X } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { getCurrentWindow } from "@tauri-apps/api/window";

const TAURI_RUNTIME = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

function useWindowControls() {
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
  return {
    maximized,
    toggleMaximize: () => void win.toggleMaximize(),
    minimize: () => void win.minimize(),
    close: () => void win.close(),
  };
}

export function AppHeader() {
  const controls = useWindowControls();

  return (
    <header className="app-header">
      <div
        className="app-header-brand"
        data-tauri-drag-region
        onDoubleClick={controls?.toggleMaximize}
        title="双击最大化/还原"
      >
        <img className="app-header-logo" src="/assets/logo.png" alt="" draggable={false} />
        <span className="app-header-wordmark" data-tauri-drag-region>
          DeepSeek Harness
        </span>
      </div>

      <div className="mode-switch" role="tablist" aria-label="应用模式">
        <button
          type="button"
          className="mode-item"
          disabled
          title="Harness 核心工作台随桌面宿主提供；当前为漫剧智能体域模式"
        >
          Harness
        </button>
        <button
          type="button"
          className="mode-item active"
          aria-current="page"
          aria-selected
          title="漫剧智能体 · 当前域模式"
        >
          漫剧智能体
        </button>
      </div>

      <div className="app-header-spacer" data-tauri-drag-region />
      <Link to="/projects/new" className="app-header-new-project" title="新建项目" draggable={false}>
        <Plus size={13} weight="bold" /> 新建项目
      </Link>

      {controls && (
        <div className="window-controls">
          <button type="button" aria-label="最小化" title="最小化" onClick={controls.minimize}>
            <Minus size={15} weight="bold" />
          </button>
          <button
            type="button"
            aria-label={controls.maximized ? "还原" : "最大化"}
            title={controls.maximized ? "还原" : "最大化"}
            onClick={controls.toggleMaximize}
          >
            {controls.maximized ? <Copy size={13} weight="bold" /> : <Square size={12} weight="bold" />}
          </button>
          <button type="button" className="close" aria-label="关闭" title="关闭" onClick={controls.close}>
            <X size={15} weight="bold" />
          </button>
        </div>
      )}
    </header>
  );
}
