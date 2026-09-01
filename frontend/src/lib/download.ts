// Shared "save this deliverable" helpers (审计 P1-2). Production outputs
// (images/videos/audio/documents) must be exportable without copy-paste
// gymnastics: an anchor with the `download` attribute forces a save dialog
// instead of the browser rendering the file inline.

import { assetUrl } from "./mediaUrl";

/** Trigger a browser download for a studio asset's immutable content. */
export function downloadAsset(assetId: string, filename?: string): void {
  const anchor = document.createElement("a");
  anchor.href = assetUrl(assetId, "content");
  if (filename) anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/** A friendly export filename derived from a version/asset label, e.g. "EP01_SH005_V2". */
export function assetFileName(label: string, mediaType?: string): string {
  const safe = label.replace(/[\\/:*?"<>|\s]+/g, "_");
  const ext = mediaType === "video" ? "mp4" : mediaType === "audio" ? "wav" : mediaType === "image" ? "png" : "";
  return ext ? `${safe}.${ext}` : safe;
}
