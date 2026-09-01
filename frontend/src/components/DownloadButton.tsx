// Shared download affordance (audit P1-2): one consistent 下载 entry point for
// every deliverable (image/video/audio asset). Icon + label match the .btn
// secondary variant used across inspectors and review surfaces.

import { DownloadSimple } from "@phosphor-icons/react";
import { assetFileName, downloadAsset } from "../lib/download";

interface DownloadButtonProps {
  assetId: string;
  /** Label used to build the export filename, e.g. "EP01_SH005_V2" or "FINAL_VIDEO". */
  label: string;
  mediaType?: string;
  className?: string;
}

export function DownloadButton({ assetId, label, mediaType, className }: DownloadButtonProps) {
  return (
    <button
      type="button"
      className={`btn secondary compact${className ? ` ${className}` : ""}`}
      onClick={() => downloadAsset(assetId, assetFileName(label, mediaType))}
      title="下载到本地"
    >
      <DownloadSimple size={14} /> 下载
    </button>
  );
}
