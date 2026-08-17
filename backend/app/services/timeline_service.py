"""TimelineService (Phase 9, api-event-contract §93) — per-episode media arrangement.

Timeline (one per episode) holds tracks (lanes) and clips (Timeline Items) whose
asset_id binds a SPECIFIC asset version (P9-T004). Edit operations are
last-write-wins (no revision guard: editing state, design §66-68). Events are
published after commit (red line).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Asset, Episode, Scene, Shot, Timeline, TimelineClip, TimelineTrack
from app.domain.timeline import (
    DEFAULT_TRACK_TYPES,
    TRACK_TYPES,
    TimelineClipCreate,
    TimelineClipUpdatePatch,
    TimelineTrackCreate,
    TimelineTrackUpdatePatch,
    TimelineUpdateRequest,
)
from app.events.bus import (
    EVENT_TIMELINE_CLIP_CREATED,
    EVENT_TIMELINE_CLIP_DELETED,
    EVENT_TIMELINE_CLIP_UPDATED,
    EVENT_TIMELINE_CREATED,
    EVENT_TIMELINE_TRACK_UPDATED,
    EVENT_TIMELINE_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import SceneRepository, ShotRepository, TimelineRepository

logger = get_logger("timeline")

DEFAULT_CLIP_DURATION = 3.0
ASSET_THUMB_BASE = "/api/v1/assets"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TimelineService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.timelines = TimelineRepository(session)
        self.scenes = SceneRepository(session)
        self.shots = ShotRepository(session)

    # ------------------------------------------------------------------ reads
    def get_timeline_for_episode(self, episode_id: str) -> dict:
        timeline = self.timelines.get_by_episode(episode_id)
        if timeline is None:
            raise NotFoundError("Episode has no timeline yet.", {"episode_id": episode_id})
        return self._timeline_read(timeline)

    def get_timeline(self, timeline_id: str) -> dict:
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
        return self._timeline_read(timeline)

    # ----------------------------------------------------------------- create
    def create_timeline(self, episode_id: str) -> dict:
        """Create the episode's timeline with the default four tracks
        (VIDEO / VOICE / MUSIC / SUBTITLE — roadmap §61)."""
        episode = self.session.get(Episode, episode_id)
        if episode is None or episode.deleted_at:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        existing = self.timelines.get_by_episode(episode_id)
        if existing is not None:
            raise ValidationError("Episode already has a timeline.", {"episode_id": episode_id})

        timeline = Timeline(project_id=episode.project_id, episode_id=episode_id, status="DRAFT")
        self.timelines.add(timeline)
        self.session.flush()  # materialize timeline.id before tracks reference it
        for order, track_type in enumerate(DEFAULT_TRACK_TYPES):
            self.session.add(
                TimelineTrack(
                    timeline_id=timeline.id,
                    track_type=track_type,
                    order_index=float(order),
                    locked=0,
                    muted=0,
                )
            )
        self.session.flush()
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_TIMELINE_CREATED,
                entity_type="timeline",
                entity_id=timeline.id,
                project_id=timeline.project_id,
                payload={"episode_id": episode_id},
            )
        )
        logger.info("timeline created: %s (episode %s)", timeline.id, episode_id)
        return self._timeline_read(timeline)

    def update_timeline(self, timeline_id: str, patch: dict) -> dict:
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
        allowed = {"duration", "width", "height", "fps", "status"}
        for key, value in patch.items():
            if key in allowed:
                setattr(timeline, key, value)
        timeline.updated_at = _now()
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_TIMELINE_UPDATED,
                entity_type="timeline",
                entity_id=timeline.id,
                project_id=timeline.project_id,
                payload=dict(patch),
            )
        )
        return self._timeline_read(timeline)

    # ----------------------------------------------------------------- tracks
    def add_track(self, timeline_id: str, data: TimelineTrackCreate) -> dict:
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
        if data.track_type not in TRACK_TYPES:
            raise ValidationError(
                "Invalid track_type.", {"track_type": data.track_type, "supported": list(TRACK_TYPES)}
            )
        order = data.order_index if data.order_index is not None else self.timelines.next_track_order(timeline_id)
        track = TimelineTrack(
            timeline_id=timeline_id,
            track_type=data.track_type,
            name=data.name,
            order_index=float(order),
            locked=0,
            muted=1 if data.track_type in ("VOICE", "MUSIC", "SFX") else 0,
        )
        self.session.add(track)
        self.session.commit()
        self._publish_track_updated(timeline, track, "created")
        return self._track_read(track)

    def update_track(self, track_id: str, patch: TimelineTrackUpdatePatch) -> dict:
        track = self.timelines.get_track(track_id)
        if track is None:
            raise NotFoundError("Track does not exist.", {"track_id": track_id})
        timeline = self.timelines.get(track.timeline_id)
        for key in ("name", "order_index", "locked", "muted"):
            value = getattr(patch, key)
            if value is not None:
                setattr(track, key, value)
        self.session.commit()
        self._publish_track_updated(timeline, track, "updated")
        return self._track_read(track)

    def delete_track(self, track_id: str) -> None:
        track = self.timelines.get_track(track_id)
        if track is None:
            raise NotFoundError("Track does not exist.", {"track_id": track_id})
        timeline = self.timelines.get(track.timeline_id)
        # explicit cascade (FK cascade needs PRAGMA ON; tests keep it off)
        for clip in self.timelines.list_track_clips(track_id):
            self.session.delete(clip)
        self.session.delete(track)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_TIMELINE_TRACK_UPDATED,
                entity_type="timeline_track",
                entity_id=track_id,
                project_id=timeline.project_id if timeline else None,
                payload={"timeline_id": track.timeline_id, "event": "deleted"},
            )
        )

    # ------------------------------------------------------------------ clips
    def add_clip(self, timeline_id: str, data: TimelineClipCreate) -> dict:
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
        track = self.timelines.get_track(data.track_id)
        if track is None or track.timeline_id != timeline_id:
            raise ValidationError("Track does not belong to this timeline.", {"track_id": data.track_id})
        asset = self.session.get(Asset, data.asset_id)
        if asset is None or asset.deleted_at or asset.project_id != timeline.project_id:
            raise ValidationError("Asset does not exist in this project.", {"asset_id": data.asset_id})
        if data.end_time <= data.start_time:
            raise ValidationError("end_time must be greater than start_time.", {})
        order = data.order_index if data.order_index is not None else self.timelines.next_clip_order(track.id)
        clip = TimelineClip(
            timeline_id=timeline_id,
            track_id=track.id,
            asset_id=data.asset_id,
            shot_id=data.shot_id,
            start_time=float(data.start_time),
            end_time=float(data.end_time),
            source_in=float(data.source_in or 0),
            source_out=data.source_out,
            order_index=float(order),
            enabled=data.enabled if data.enabled is not None else 1,
            text=None,
        )
        self.session.add(clip)
        self.session.flush()
        if timeline.duration is None or clip.end_time > timeline.duration:
            timeline.duration = clip.end_time
        self.session.commit()
        self._publish_clip(timeline, clip, "created")
        return self._clip_read(clip)

    def update_clip(self, clip_id: str, patch: TimelineClipUpdatePatch) -> dict:
        clip = self.timelines.get_clip(clip_id)
        if clip is None:
            raise NotFoundError("Clip does not exist.", {"clip_id": clip_id})
        timeline = self.timelines.get(clip.timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": clip.timeline_id})

        new_track_id = patch.track_id if patch.track_id is not None else clip.track_id
        track = self.timelines.get_track(new_track_id)
        if track is None or track.timeline_id != clip.timeline_id:
            raise ValidationError("Target track does not belong to this timeline.", {"track_id": new_track_id})

        if patch.start_time is not None:
            clip.start_time = float(patch.start_time)
        if patch.end_time is not None:
            clip.end_time = float(patch.end_time)
        if patch.source_in is not None:
            clip.source_in = float(patch.source_in)
        if patch.source_out is not None:
            clip.source_out = patch.source_out
        if patch.track_id is not None:
            clip.track_id = new_track_id
        if patch.order_index is not None:
            clip.order_index = float(patch.order_index)
        if patch.enabled is not None:
            clip.enabled = int(patch.enabled)

        if clip.end_time <= clip.start_time:
            raise ValidationError("end_time must be greater than start_time.", {})

        clip.updated_at = _now()
        if timeline.duration is None or clip.end_time > timeline.duration:
            timeline.duration = clip.end_time
        self.session.commit()
        self._publish_clip(timeline, clip, "updated")
        return self._clip_read(clip)

    def delete_clip(self, clip_id: str) -> None:
        clip = self.timelines.get_clip(clip_id)
        if clip is None:
            raise NotFoundError("Clip does not exist.", {"clip_id": clip_id})
        timeline = self.timelines.get(clip.timeline_id)
        self.session.delete(clip)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_TIMELINE_CLIP_DELETED,
                entity_type="timeline_clip",
                entity_id=clip_id,
                project_id=timeline.project_id if timeline else None,
                payload={"timeline_id": clip.timeline_id},
            )
        )

    def replace_clip_asset(self, clip_id: str, asset_id: str) -> dict:
        """P9-T012: rebind a clip to another asset/version."""
        clip = self.timelines.get_clip(clip_id)
        if clip is None:
            raise NotFoundError("Clip does not exist.", {"clip_id": clip_id})
        timeline = self.timelines.get(clip.timeline_id)
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at or (timeline and asset.project_id != timeline.project_id):
            raise ValidationError("Asset does not exist in this project.", {"asset_id": asset_id})
        clip.asset_id = asset_id
        clip.updated_at = _now()
        self.session.commit()
        self._publish_clip(timeline, clip, "updated")
        return self._clip_read(clip)

    # -------------------------------------------------------- one-click arrange
    def sequence_from_shots(self, timeline_id: str) -> dict:
        """P9-E1/E2 helper: rebuild VIDEO + SUBTITLE tracks from the episode's shots.

        - For every shot (scene_number → shot_order), bind the shot's active video
          asset, falling back to its active image asset; skip shots with neither.
        - VIDEO clips are laid back-to-back (duration = shot.duration or 3s).
        - A SUBTITLE clip (text = shot.dialogue) is added on the same window when
          the shot has dialogue.
        - Existing VIDEO/SUBTITLE clips are replaced (one-click arrange).
        """
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
        episode_id = timeline.episode_id

        video_track = subtitle_track = None
        for track in self.timelines.list_tracks(timeline_id):
            if track.track_type == "VIDEO" and video_track is None:
                video_track = track
            elif track.track_type == "SUBTITLE" and subtitle_track is None:
                subtitle_track = track
        if video_track is None:
            raise ValidationError("Timeline has no VIDEO track.", {})

        # clear existing VIDEO/SUBTITLE clips
        keep = {video_track.id}
        if subtitle_track is not None:
            keep.add(subtitle_track.id)
        for clip in self.timelines.list_clips(timeline_id):
            if clip.track_id in keep:
                self.session.delete(clip)
        self.session.flush()

        scenes = self._scenes_ordered(episode_id)

        cursor = 0.0
        order = 0.0
        created_clips: list[TimelineClip] = []
        for scene in scenes:
            for shot in self._shots_ordered(scene.id):
                asset_id = shot.active_video_asset_id or shot.active_image_asset_id
                if not asset_id or not self.session.get(Asset, asset_id):
                    continue
                duration = shot.duration or DEFAULT_CLIP_DURATION
                clip = TimelineClip(
                    timeline_id=timeline_id,
                    track_id=video_track.id,
                    asset_id=asset_id,
                    shot_id=shot.id,
                    start_time=cursor,
                    end_time=cursor + duration,
                    source_in=0.0,
                    source_out=None,
                    order_index=order,
                    enabled=1,
                    text=None,
                )
                self.session.add(clip)
                created_clips.append(clip)
                order += 1
                if subtitle_track is not None and shot.dialogue:
                    sub = TimelineClip(
                        timeline_id=timeline_id,
                        track_id=subtitle_track.id,
                        asset_id=asset_id,
                        shot_id=shot.id,
                        start_time=cursor,
                        end_time=cursor + duration,
                        source_in=0.0,
                        source_out=None,
                        order_index=order,
                        enabled=1,
                        text=shot.dialogue,
                    )
                    self.session.add(sub)
                    order += 1
                cursor += duration

        timeline.duration = cursor
        self.session.commit()
        for clip in created_clips:
            self._publish_clip(timeline, clip, "created")
        return self._timeline_read(timeline)

    def _scenes_ordered(self, episode_id: str) -> list[Scene]:
        stmt = select(Scene).where(Scene.episode_id == episode_id).order_by(Scene.scene_number, Scene.scene_order)
        return list(self.session.scalars(stmt))

    def _shots_ordered(self, scene_id: str) -> list[Shot]:
        stmt = select(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None)).order_by(Shot.shot_order, Shot.shot_number)
        return list(self.session.scalars(stmt))

    # ------------------------------------------------------------ preview (P9-T013)
    def generate_preview(self, timeline_id: str) -> str | None:
        """Compose a non-render contact-sheet JPEG of the VIDEO-track clip assets.

        Pure PIL (no encoder): first frame of each enabled VIDEO clip, laid out
        horizontally with a clip index strip header. Best-effort — returns None
        when there is nothing to preview. Used by GET /timelines/{id}/preview.
        """
        try:
            from PIL import Image

            timeline = self.timelines.get(timeline_id)
            if timeline is None:
                raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})
            track_by_id = {t.id: t for t in self.timelines.list_tracks(timeline.id)}
            clips = sorted(
                (c for c in self.timelines.list_clips(timeline.id) if c.enabled),
                key=lambda c: (c.start_time, c.order_index),
            )
            video_clips = [c for c in clips if track_by_id.get(c.track_id) and track_by_id[c.track_id].track_type == "VIDEO"]
            if not video_clips:
                return None
            from app.core.config import settings
            from app.services.asset_service import AssetService

            asset_svc = AssetService(self.session)
            thumb_h = 240
            per_w = 160
            strip = Image.new("RGB", (per_w * min(len(video_clips), 24), thumb_h + 22), (18, 20, 26))
            from PIL import ImageDraw

            draw = ImageDraw.Draw(strip)
            used = 0
            for clip in video_clips[:24]:
                x = used * per_w
                draw.rectangle([x, 0, x + per_w - 1, thumb_h + 20], outline=(60, 66, 78))
                asset = self.session.get(Asset, clip.asset_id) if clip.asset_id else None
                if asset and asset.file_path:
                    try:
                        path = asset_svc.absolute_path(asset)
                        with Image.open(path) as img:
                            frame = img.convert("RGB")
                        ratio = thumb_h / max(1, frame.height)
                        tw = max(1, int(frame.width * ratio))
                        th = max(1, int(frame.height * ratio))
                        thumb = frame.resize((tw, th), Image.LANCZOS)
                        left = max(0, (tw - per_w) // 2)
                        strip.paste(thumb.crop((left, 0, left + per_w, th)), (x, 0))
                    except Exception:  # noqa: BLE001 — missing file → labeled block
                        draw.rectangle([x, 0, x + per_w - 1, thumb_h - 1], fill=(35, 39, 47))
                else:
                    draw.rectangle([x, 0, x + per_w - 1, thumb_h - 1], fill=(35, 39, 47))
                label = f"{clip.start_time:.1f}s"
                draw.text((x + 6, thumb_h + 4), label[:14], fill=(200, 205, 214))
                used += 1
            preview_dir = settings.data_dir / "previews"
            preview_dir.mkdir(parents=True, exist_ok=True)
            out = preview_dir / f"timeline_{timeline_id[-6:]}.jpg"
            strip.save(out, "JPEG", quality=82)
            return str(out)
        except Exception as exc:  # noqa: BLE001 — preview is best-effort
            logger.warning("timeline preview failed: %s", exc)
            return None

    # ------------------------------------------------------------------ helpers
    def _publish_track_updated(self, timeline, track, event: str) -> None:
        bus.publish(
            StudioEvent(
                event_type=EVENT_TIMELINE_TRACK_UPDATED,
                entity_type="timeline_track",
                entity_id=track.id,
                project_id=timeline.project_id if timeline else None,
                payload={"timeline_id": track.timeline_id, "track_type": track.track_type, "event": event},
            )
        )

    def _publish_clip(self, timeline, clip, event: str) -> None:
        event_type = {
            "created": EVENT_TIMELINE_CLIP_CREATED,
            "updated": EVENT_TIMELINE_CLIP_UPDATED,
            "deleted": EVENT_TIMELINE_CLIP_DELETED,
        }[event]
        bus.publish(
            StudioEvent(
                event_type=event_type,
                entity_type="timeline_clip",
                entity_id=clip.id,
                project_id=timeline.project_id if timeline else None,
                payload={"timeline_id": clip.timeline_id, "track_id": clip.track_id},
            )
        )

    def _asset_summary(self, asset: Asset | None) -> dict | None:
        if asset is None:
            return None
        return {
            "id": asset.id,
            "type": asset.type,
            "name": asset.name,
            "status": asset.status,
            "version_group_id": asset.version_group_id,
            "version_number": asset.version_number,
            "thumbnail_url": f"{ASSET_THUMB_BASE}/{asset.id}/thumbnail" if asset.thumbnail_path else None,
            "mime_type": asset.mime_type,
        }

    def _track_read(self, track: TimelineTrack) -> dict:
        return {
            "id": track.id,
            "timeline_id": track.timeline_id,
            "track_type": track.track_type,
            "name": track.name,
            "order_index": float(track.order_index),
            "locked": int(track.locked or 0),
            "muted": int(track.muted or 0),
            "created_at": track.created_at,
        }

    def _clip_read(self, clip: TimelineClip) -> dict:
        asset = self.session.get(Asset, clip.asset_id) if clip.asset_id else None
        return {
            "id": clip.id,
            "timeline_id": clip.timeline_id,
            "track_id": clip.track_id,
            "asset_id": clip.asset_id,
            "shot_id": clip.shot_id,
            "start_time": float(clip.start_time),
            "end_time": float(clip.end_time),
            "source_in": float(clip.source_in or 0),
            "source_out": clip.source_out,
            "order_index": float(clip.order_index),
            "enabled": int(clip.enabled) if clip.enabled is not None else 1,
            "text": clip.text,
            "asset": self._asset_summary(asset),
            "created_at": clip.created_at,
            "updated_at": clip.updated_at,
        }

    def _timeline_read(self, timeline: Timeline) -> dict:
        tracks = [self._track_read(t) for t in self.timelines.list_tracks(timeline.id)]
        clips = [self._clip_read(c) for c in self.timelines.list_clips(timeline.id)]
        return {
            "id": timeline.id,
            "project_id": timeline.project_id,
            "episode_id": timeline.episode_id,
            "duration": timeline.duration,
            "width": timeline.width,
            "height": timeline.height,
            "fps": timeline.fps,
            "status": timeline.status,
            "tracks": tracks,
            "clips": clips,
            "created_at": timeline.created_at,
            "updated_at": timeline.updated_at,
        }