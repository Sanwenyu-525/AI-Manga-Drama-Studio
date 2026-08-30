// Tauri shell (mvp-spec DT-001..004). The shell stays thin: window + tray + file dialogs.
// All business logic lives in the local FastAPI backend (127.0.0.1:17820) + React frontend.
//
// DT-003 + P1-E5-T02: the shell manages the backend lifecycle (probe the /health
// handshake, spawn on startup with a per-session STUDIO_SESSION_TOKEN if the port
// is free, expose that token to the webview, and terminate our own spawned child
// on exit — never touch a user-started backend).

mod backend;

use backend::{
    BackendRuntime, BackendState, ensure_backend, get_session_token, stop_spawned_backend,
};
use std::sync::Mutex;
use tauri::Manager; // app_handle()/state() on Window/AppHandle

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init()) // 原生目录对话框（设置页「浏览」）
        .manage(BackendState(Mutex::new(BackendRuntime {
            child: None,
            session_token: None,
        })))
        .invoke_handler(tauri::generate_handler![get_session_token])
        .setup(|app| {
            ensure_backend(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            // Last window closed → clean up the backend we spawned (best-effort).
            if let tauri::WindowEvent::Destroyed = event {
                stop_spawned_backend(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
