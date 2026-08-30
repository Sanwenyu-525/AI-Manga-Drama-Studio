// Honest shot thumbnail: renders the real thumbnail when the shot has one, and an
// explicit 未生成 placeholder otherwise — never a stock-looking image that could be
// mistaken for a generated frame (DESIGN.md honesty rule / P12 中文化).

import { ImageSquare } from "@phosphor-icons/react";

interface ShotThumbShot {
  thumbnail_url?: string | null;
  shot_number: number;
}

export function ShotThumbImage({ shot, className }: { shot: ShotThumbShot; className?: string }) {
  if (shot.thumbnail_url) {
    return <img loading="lazy" src={shot.thumbnail_url} alt={`Shot ${shot.shot_number}`} className={className} />;
  }
  return (
    <span className={`shot-thumb-empty${className ? ` ${className}` : ""}`} role="img" aria-label={`Shot ${shot.shot_number} 未生成`}>
      <ImageSquare size={18} weight="regular" aria-hidden />
      <strong>SH{String(shot.shot_number).padStart(2, "0")}</strong>
      <span>暂无预览图</span>
    </span>
  );
}
