// Session-aware media URL builder (审计 P0-5). <img>/<video>/<audio>/<a download>
// cannot send the X-Session-Token header that the backend's local session auth
// middleware requires (app/main.py local_session_auth), so in the Tauri shell
// every media tag silently 401s. The middleware accepts the same token via
// ?token= (the same pattern the WS gateway already uses, events/ws.py), so we
// append it here when present. In plain-browser dev there is no token and the
// URL is returned untouched.

import { getSessionToken } from "./session";

export function mediaUrl(path: string): string {
  const token = getSessionToken();
  if (!token) return path;
  // The path may already carry a query string (e.g. the timeline preview's
  // cache-busting `?v=`) — append with `&` in that case, otherwise `?`
  // produces a malformed URL where the token never reaches the backend.
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}token=${encodeURIComponent(token)}`;
}

export function assetUrl(assetId: string, kind: "content" | "thumbnail" = "content"): string {
  return mediaUrl(`/api/v1/assets/${assetId}/${kind}`);
}
