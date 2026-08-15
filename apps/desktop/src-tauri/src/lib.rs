// Tauri shell (mvp-spec DT-001..004). The shell stays thin: window + tray + file dialogs.
// All business logic lives in the local FastAPI backend (127.0.0.1:17820) + React frontend.
//
// DT-003: the shell manages the backend lifecycle (spawn on startup if the port is free,
// terminate our own spawned child on exit — never touch a user-started backend).

mod backend;

use backend::{BackendState, ensure_backend, stop_spawned_backend};
use std::sync::Mutex;
use tauri::Manager; // app_handle()/state() on Window/AppHandle

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendState(Mutex::new(None)))
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
