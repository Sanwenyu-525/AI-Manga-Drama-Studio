// DT-003: backend process management (mvp-spec §13).
//
// The shell keeps the local FastAPI backend alive:
// - On startup: probe TCP 127.0.0.1:17820; if nothing listens, spawn the backend
//   (`uv run uvicorn app.main:app ...` inside backend/), detached from the console.
// - On window close: terminate the spawned backend (best-effort, only if WE spawned it —
//   a user-started backend is left alone).
// Lightweight by design: no self-healing, no watchdog (Phase 2+ if needed).

use std::net::TcpStream;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{AppHandle, Manager};

pub const BACKEND_PORT: u16 = 17820;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub struct BackendState(pub Mutex<Option<Child>>);

/// Probe whether something already listens on the backend port.
fn port_in_use(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn backend_dir() -> PathBuf {
    // apps/desktop/src-tauri → repo root → backend/
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .ancestors()
        .nth(3) // 0=src-tauri, 1=desktop, 2=apps, 3=repo root
        .unwrap_or(manifest_dir.as_path())
        .join("backend")
}

/// Ensure the backend is running; spawn it if needed. Idempotent.
pub fn ensure_backend(app: &AppHandle) -> bool {
    eprintln!("[studio] ensure_backend: probing 127.0.0.1:{}", BACKEND_PORT);
    if port_in_use(BACKEND_PORT) {
        eprintln!("[studio] backend already running on :{}", BACKEND_PORT);
        return true; // already running (user-started or previous spawn)
    }
    let state = app.state::<BackendState>();
    let mut guard = state.0.lock().expect("backend state lock");
    if guard.is_some() {
        eprintln!("[studio] backend already spawned by us");
        return true; // we already spawned it
    }

    let dir = backend_dir();
    eprintln!("[studio] spawning backend in {:?}", dir);
    let child = Command::new("uv")
        .args([
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            &BACKEND_PORT.to_string(),
        ])
        .current_dir(&dir)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn();

    match child {
        Ok(child) => {
            eprintln!("[studio] spawned backend pid={:?}", child.id());
            *guard = Some(child);
            true
        }
        Err(err) => {
            eprintln!(
                "[studio] failed to spawn backend: {err}; run it manually on :{}",
                BACKEND_PORT
            );
            false
        }
    }
}

/// Stop the backend we spawned (best-effort; never touches user-started processes).
pub fn stop_spawned_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let mut guard = state.0.lock().expect("backend state lock");
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
        eprintln!("[studio] stopped spawned backend");
    }
}
