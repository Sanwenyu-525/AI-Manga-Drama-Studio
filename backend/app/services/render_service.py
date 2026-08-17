"""RenderService (Phase 9, P9-E3) — the Timeline → Episode render boundary.

Queues episode renders as type="render" Generations (the generation queue IS the
job queue in this MVP, roadmap P9-T015). The worker executes them through a
RenderProvider; the produced file registers as a FINAL_VIDEO asset under
"vg:episode:{episode_id}:FINAL_VIDEO" (type=video, immutable versions).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Asset, Generation, Project, Timeline
from app.events.bus import EVENT_GENERATION_QUEUED, StudioEvent, bus
from app.providers.registry import resolve_render_provider_id
from app.repositories import TimelineRepository

logger = get_logger("render")

FINAL_VIDEO_GROUP = "FINAL_VIDEO"
DEFAULT_FPS = 24.0
DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 1280
MAX_RENDER_CLIPS = 200


def _now() -> str:
    return datetime.now(UTC).isoformat()


def final_video_version_group(episode_id: str) -> str:
    """Version group of an episode export (ADR-001 style)."""
    return "vg:episode:" + episode_id + ":" + FINAL_VIDEO_GROUP


class RenderService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.timelines = TimelineRepository(session)

    # ----------------------------------------------------------------- queue
    def create_render_generation(self, timeline_id: str, provider: str | None = None) -> Generation:
        """Queue an episode render as a type="render" Generation (202 path)."""
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
        plan = self._resolve_render_plan(timeline)
        if not plan["clips"]:
            raise ValidationError(
                "Timeline has no enabled VIDEO clips. Add clips (e.g. sequence-from-shots) before rendering.",
                {"timeline_id": timeline_id},
            )

        pid = resolve_render_provider_id(provider)
        parameters = json.dumps(
            {
                "timeline_id": timeline_id,
                "episode_id": timeline.episode_id,
                "fps": plan["fps"],
                "width": plan["width"],
                "height": plan["height"],
                "clips": [
                    {
                        "asset_id": c["asset_id"],
                        "kind": c["kind"],
                        "start": c["start"],
                        "end": c["end"],
                        "source_in": c.get("source_in", 0),
                        "source_out": c.get("source_out"),
                        "text": c.get("text"),
                    }
                    for c in plan["clips"]
                ],
            },
            ensure_ascii=False,
        )
        generation = Generation(
            project_id=timeline.project_id,
            shot_id=None,
            type="render",
            provider=pid,
            status="queued",
            parameters=parameters,
            progress=0,
            stage="queued",
            max_attempts=1,
        )
        self.session.add(generation)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_QUEUED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=timeline.project_id,
                payload={"timeline_id": timeline_id, "episode_id": timeline.episode_id, "type": "render"},
            )
        )
        logger.info(
            "render generation queued: %s (timeline %s, provider %s, %d clip(s))",
            generation.id, timeline_id, pid, len(plan["clips"]),
        )
        return generation

    # ----------------------------------------------------------- plan resolve
    def _resolve_render_plan(self, timeline: Timeline) -> dict:
        """Collect enabled VIDEO-track clips in chronological order (resolved assets)."""
        project = self.session.get(Project, timeline.project_id) if timeline.project_id else None
        fps = timeline.fps or (project.fps if project and project.fps else DEFAULT_FPS)
        width = timeline.width or DEFAULT_WIDTH
        height = timeline.height or DEFAULT_HEIGHT

        track_by_id = {t.id: t for t in self.timelines.list_tracks(timeline.id)}
        clips = sorted(
            (c for c in self.timelines.list_clips(timeline.id) if c.enabled),
            key=lambda c: (c.start_time, c.order_index),
        )
        resolved = []
        for clip in clips[:MAX_RENDER_CLIPS]:
            track = track_by_id.get(clip.track_id)
            if track is None or track.track_type != "VIDEO":
                continue
            asset = self.session.get(Asset, clip.asset_id) if clip.asset_id else None
            if asset is None or asset.deleted_at:
                continue
            resolved.append(
                {
                    "clip_id": clip.id,
                    "asset_id": asset.id,
                    "kind": "image" if asset.type == "image" else "video",
                    "start": float(clip.start_time),
                    "end": float(clip.end_time),
                    "source_in": float(clip.source_in or 0),
                    "source_out": clip.source_out,
                    "text": clip.text,
                },
            )
        return {"fps": float(fps), "width": int(width), "height": int(height), "clips": resolved}

    # ------------------------------------------------------------ final video
    def get_final_video(self, episode_id: str) -> dict | None:
        """The newest rendered export (FINAL_VIDEO asset) of an episode, or None."""
        group = final_video_version_group(episode_id)
        asset = self.session.scalars(
            select(Asset)
            .where(
                Asset.version_group_id == group,
                Asset.deleted_at.is_(None),
            )
            .order_by(Asset.version_number.desc())
            .limit(1),
        ).first()
        return self._final_video_read(asset, episode_id) if asset else None

    def _final_video_read(self, asset: Asset, episode_id: str) -> dict:
        meta = {}
        if asset.meta_json:
            try:
                meta = json.loads(asset.meta_json)
            except (ValueError, TypeError):
                meta = {}
        return {
            "asset_id": asset.id,
            "project_id": asset.project_id,
            "episode_id": episode_id,
            "name": asset.name,
            "type": asset.type,
            "version_number": asset.version_number,
            "mime_type": asset.mime_type,
            "duration": asset.duration,
            "width": asset.width,
            "height": asset.height,
            "file_size": asset.file_size,
            "status": asset.status,
            "content_url": "/api/v1/assets/" + asset.id + "/content",
            "thumbnail_url": ("/api/v1/assets/" + asset.id + "/thumbnail") if asset.thumbnail_path else None,
            "meta": meta or None,
            "created_at": asset.created_at,
        }
