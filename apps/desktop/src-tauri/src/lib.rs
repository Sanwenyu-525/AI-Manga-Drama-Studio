// Tauri shell (mvp-spec DT-001..004). The shell stays thin: window + tray + file dialogs.
// All business logic lives in the local FastAPI backend (127.0.0.1:17820) + React frontend.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
