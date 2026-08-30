// DT-003: backend process management (mvp-spec §13) + P1-E5-T02 local session.
//
// The shell keeps the local FastAPI backend alive:
// - On startup: probe the backend's /health handshake. If a STUDIO instance is
//   already listening, adopt it. If the port is occupied by a DIFFERENT process,
//   refuse to spawn (distinguishing "port busy by another app" from "this app's
//   backend already running"). Otherwise spawn the backend (`uv run uvicorn ...`)
//   with a fresh per-session token in STUDIO_SESSION_TOKEN.
// - The session token is exposed to the webview via get_session_token so the
//   frontend can authenticate REST/WS against the local control plane.
// - On window close: terminate the backend we spawned (best-effort, only if WE
//   spawned it — a user-started backend is left alone).

use std::io::{Read, Write};
use std::net::TcpStream;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager};

pub const BACKEND_PORT: u16 = 17820;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const HEALTH_PATH: &str = "/api/v1/health";

pub struct BackendState(pub Mutex<BackendRuntime>);

pub struct BackendRuntime {
    pub child: Option<Child>,
    pub session_token: Option<String>,
}

/// Raw HTTP GET to the backend (no HTTP client dep needed for a one-shot handshake).
fn http_get(path: &str) -> Option<String> {
    let mut stream = TcpStream::connect(("127.0.0.1", BACKEND_PORT)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(3))).ok()?;
    stream.set_write_timeout(Some(Duration::from_secs(3))).ok()?;
    let req = format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
    stream.write_all(req.as_bytes()).ok()?;
    let mut buf = Vec::new();
    stream.read_to_end(&mut buf).ok()?;
    Some(String::from_utf8_lossy(&buf).into_owned())
}

enum BackendProbe {
    /// /health responded with our marker → an instance of this app is running.
    ThisStudio,
    /// Port open but the response is not a Studio backend → another process.
    OtherProcess,
    /// Nothing listens (or the probe timed out) → safe to spawn.
    Nothing,
}

/// P1-E5-T02: distinguish "this app already running" from "port busy by another app".
fn probe_backend() -> BackendProbe {
    let body = match http_get(HEALTH_PATH) {
        Some(body) => body,
        None => return BackendProbe::Nothing,
    };
    if body.contains("backend_version") {
        BackendProbe::ThisStudio
    } else {
        BackendProbe::OtherProcess
    }
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
    eprintln!("[studio] probing 127.0.0.1:{BACKEND_PORT} ({}...)", HEALTH_PATH);
    match probe_backend() {
        BackendProbe::ThisStudio => {
            eprintln!("[studio] studio backend already running on :{BACKEND_PORT}");
            return true;
        }
        BackendProbe::OtherProcess => {
            eprintln!(
                "[studio] port :{BACKEND_PORT} is occupied by ANOTHER process — refusing to spawn (not a studio backend)"
            );
            return false;
        }
        BackendProbe::Nothing => {}
    }

    let state = app.state::<BackendState>();
    let mut guard = state.0.lock().expect("backend state lock");
    if guard.child.is_some() {
        eprintln!("[studio] backend already spawned by us");
        return true;
    }

    // Fresh high-entropy per-session token: the backend enforces it (REST header /
    // WS query) so only THIS session can call the local control plane.
    let token = uuid::Uuid::new_v4().simple().to_string();
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
        .env("STUDIO_SESSION_TOKEN", &token)
        .current_dir(&dir)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn();

    match child {
        Ok(child) => {
            eprintln!("[studio] spawned backend pid={:?}", child.id());
            guard.child = Some(child);
            guard.session_token = Some(token);
            true
        }
        Err(err) => {
            eprintln!(
                "[studio] failed to spawn backend: {err}; run it manually on :{BACKEND_PORT}"
            );
            false
        }
    }
}

/// Expose the current session token to the webview (None if we didn't spawn the
/// backend — e.g. a user-started dev backend, whose auth is off anyway).
#[tauri::command]
pub fn get_session_token(app: AppHandle) -> Option<String> {
    let state = app.state::<BackendState>();
    let guard = state.0.lock().expect("backend state lock");
    guard.session_token.clone()
}

/// Stop the backend we spawned (best-effort; never touches user-started processes).
pub fn stop_spawned_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let mut guard = state.0.lock().expect("backend state lock");
    if let Some(mut child) = guard.child.take() {
        let _ = child.kill();
        let _ = child.wait();
        guard.session_token = None;
        eprintln!("[studio] stopped spawned backend");
    }
}
