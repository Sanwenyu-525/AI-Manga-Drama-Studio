// Local session token (P1-E5-T02): the Tauri shell generates a per-session token,
// hands it to the spawned backend (STUDIO_SESSION_TOKEN) and exposes it to the
// webview via the get_session_token command. The frontend forwards it on every
// REST request (X-Session-Token) and the WS URL (?token=) so that only this
// session can call the local control plane.
//
// In a plain browser (dev at :17821) there is no shell, so invoke() throws and
// the token stays null — the backend then has no token configured (dev-shell
// backend) and auth is off, keeping the browser dev flow convenient.

import { invoke } from "@tauri-apps/api/core";

let sessionToken: string | null = null;
let tokenPromise: Promise<string | null> | null = null;

export function initSessionToken(): Promise<string | null> {
  if (!tokenPromise) {
    tokenPromise = (async () => {
      try {
        sessionToken = await invoke<string>("get_session_token");
      } catch {
        sessionToken = null; // not running under the Tauri shell → no token
      }
      return sessionToken;
    })();
  }
  return tokenPromise;
}

export function getSessionToken(): string | null {
  return sessionToken;
}
