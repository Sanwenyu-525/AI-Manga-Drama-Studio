// Shared fullscreen preview overlay (audit P2-10). Previously only AssetsPage
// had a lightbox while ShotInspector versions could not be enlarged at all;
// this is the single extracted primitive reusing the existing .lightbox CSS:
// click backdrop or press ESC to close, optional actions (download) and caption.

import { useEffect } from "react";
import { X } from "@phosphor-icons/react";

interface LightboxProps {
  open: boolean;
  onClose: () => void;
  /** Full-size media URL (already token-aware via lib/mediaUrl). */
  src: string | null;
  alt: string;
  /** Render <video> instead of <img> for video assets. */
  mediaType?: string;
  /** Action buttons rendered top-left beside the close button. */
  actions?: React.ReactNode;
  /** Caption rendered under the media (uses .lightbox-meta). */
  caption?: React.ReactNode;
}

export function Lightbox({ open, onClose, src, alt, mediaType, actions, caption }: LightboxProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !src) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={alt} onClick={onClose}>
      <div className="lightbox-inner" onClick={(event) => event.stopPropagation()}>
        {actions && <div className="lightbox-actions">{actions}</div>}
        <button className="icon-button lightbox-close" aria-label="关闭预览" onClick={onClose}>
          <X size={18} />
        </button>
        {mediaType === "video" ? (
          <video src={src} controls autoPlay loop muted />
        ) : (
          <img src={src} alt={alt} />
        )}
        {caption && <div className="lightbox-meta">{caption}</div>}
      </div>
    </div>
  );
}
