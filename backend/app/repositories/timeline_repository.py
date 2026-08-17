"""Timeline repository (Phase 9) — timeline/track/clip persistence.

Timeline entities are content-editing state: no soft delete (last-write-wins,
design §66-68). Tracks/clips cascade-delete with their timeline/track.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.timeline import Timeline, TimelineClip, TimelineTrack


class TimelineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- timeline ---
    def get(self, timeline_id: str) -> Timeline | None:
        return self.session.get(Timeline, timeline_id)

    def get_by_episode(self, episode_id: str) -> Timeline | None:
        return self.session.scalars(
            select(Timeline).where(Timeline.episode_id == episode_id)
        ).first()

    def add(self, timeline: Timeline) -> Timeline:
        self.session.add(timeline)
        return timeline

    # --- tracks ---
    def list_tracks(self, timeline_id: str) -> list[TimelineTrack]:
        return list(
            self.session.scalars(
                select(TimelineTrack)
                .where(TimelineTrack.timeline_id == timeline_id)
                .order_by(TimelineTrack.order_index, TimelineTrack.created_at)
            )
        )

    def get_track(self, track_id: str) -> TimelineTrack | None:
        return self.session.get(TimelineTrack, track_id)

    def next_track_order(self, timeline_id: str) -> float:
        current = self.session.scalar(
            select(func.max(TimelineTrack.order_index)).where(
                TimelineTrack.timeline_id == timeline_id
            )
        )
        return float((current or 0) + 1)

    def count_tracks(self, timeline_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(TimelineTrack).where(
                    TimelineTrack.timeline_id == timeline_id
                )
            )
            or 0
        )

    # --- clips ---
    def list_clips(self, timeline_id: str) -> list[TimelineClip]:
        return list(
            self.session.scalars(
                select(TimelineClip)
                .where(TimelineClip.timeline_id == timeline_id)
                .order_by(TimelineClip.start_time, TimelineClip.order_index, TimelineClip.created_at)
            )
        )

    def list_track_clips(self, track_id: str) -> list[TimelineClip]:
        return list(
            self.session.scalars(
                select(TimelineClip)
                .where(TimelineClip.track_id == track_id)
                .order_by(TimelineClip.start_time, TimelineClip.order_index)
            )
        )

    def get_clip(self, clip_id: str) -> TimelineClip | None:
        return self.session.get(TimelineClip, clip_id)

    def next_clip_order(self, track_id: str) -> float:
        current = self.session.scalar(
            select(func.max(TimelineClip.order_index)).where(TimelineClip.track_id == track_id)
        )
        return float((current or 0) + 1)
