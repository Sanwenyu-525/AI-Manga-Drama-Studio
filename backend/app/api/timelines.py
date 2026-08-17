"""Timeline API (api-event-contract §93, Phase 9 — Timeline & Episode Render).

Per-episode timeline CRUD (tracks + clips + version replace), one-click
sequence-from-shots, non-render preview, render queueing (202) and the
rendered FINAL_VIDEO export. Router stays thin: TimelineService / RenderService
own all business logic (red line).
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.timeline import (
    FinalVideoRead,
    TimelineClipCreate,
    TimelineClipRead,
    TimelineClipReplaceRequest,
    TimelineClipUpdateRequest,
    TimelineRead,
    TimelineRenderRead,
    TimelineTrackCreate,
    TimelineTrackRead,
    TimelineTrackUpdateRequest,
    TimelineUpdateRequest,
)
from app.services.render_service import RenderService
from app.services.timeline_service import TimelineService

router = APIRouter(tags=["timeline"])


def _tl_read(service: TimelineService, data: dict) -> TimelineRead:
    return TimelineRead(**data)


@router.get("/episodes/{episode_id}/timeline", response_model=TimelineRead)
def get_episode_timeline(episode_id: str, db: Session = Depends(get_db)) -> TimelineRead:
    """The episode’s timeline (404 when not created yet)."""
    return _tl_read(TimelineService(db), TimelineService(db).get_timeline_for_episode(episode_id))


@router.post("/episodes/{episode_id}/timeline", response_model=TimelineRead, status_code=status.HTTP_201_CREATED)
def create_episode_timeline(episode_id: str, db: Session = Depends(get_db)) -> TimelineRead:
    """Create the episode’s timeline with the default four tracks."""
    return _tl_read(TimelineService(db), TimelineService(db).create_timeline(episode_id))



@router.get("/timelines/{timeline_id}", response_model=TimelineRead)
def get_timeline(timeline_id: str, db: Session = Depends(get_db)) -> TimelineRead:
    return _tl_read(TimelineService(db), TimelineService(db).get_timeline(timeline_id))
@router.patch("/timelines/{timeline_id}", response_model=TimelineRead)
def update_timeline(timeline_id: str, data: TimelineUpdateRequest, db: Session = Depends(get_db)) -> TimelineRead:
    return _tl_read(TimelineService(db), TimelineService(db).update_timeline(timeline_id, data.patch.model_dump(exclude_unset=True)))


@router.post("/timelines/{timeline_id}/tracks", response_model=TimelineTrackRead, status_code=status.HTTP_201_CREATED)
def add_track(timeline_id: str, data: TimelineTrackCreate, db: Session = Depends(get_db)) -> TimelineTrackRead:
    return TimelineTrackRead(**TimelineService(db).add_track(timeline_id, data))


@router.patch("/timelines/{timeline_id}/tracks/{track_id}", response_model=TimelineTrackRead)
def update_track(timeline_id: str, track_id: str, data: TimelineTrackUpdateRequest, db: Session = Depends(get_db)) -> TimelineTrackRead:
    return TimelineTrackRead(**TimelineService(db).update_track(track_id, data.patch))


@router.delete("/timelines/{timeline_id}/tracks/{track_id}", status_code=status.HTTP_200_OK)
def delete_track(timeline_id: str, track_id: str, db: Session = Depends(get_db)) -> dict:
    TimelineService(db).delete_track(track_id)
    return {"id": track_id, "deleted": True}


@router.post("/timelines/{timeline_id}/clips", response_model=TimelineClipRead, status_code=status.HTTP_201_CREATED)
def add_clip(timeline_id: str, data: TimelineClipCreate, db: Session = Depends(get_db)) -> TimelineClipRead:
    return TimelineClipRead(**TimelineService(db).add_clip(timeline_id, data))


@router.patch("/timeline-clips/{clip_id}", response_model=TimelineClipRead)
def update_clip(clip_id: str, data: TimelineClipUpdateRequest, db: Session = Depends(get_db)) -> TimelineClipRead:
    return TimelineClipRead(**TimelineService(db).update_clip(clip_id, data.patch))


@router.delete("/timeline-clips/{clip_id}", status_code=status.HTTP_200_OK)
def delete_clip(clip_id: str, db: Session = Depends(get_db)) -> dict:
    TimelineService(db).delete_clip(clip_id)
    return {"id": clip_id, "deleted": True}


@router.post("/timeline-clips/{clip_id}/replace-asset", response_model=TimelineClipRead)
def replace_clip_asset(clip_id: str, data: TimelineClipReplaceRequest, db: Session = Depends(get_db)) -> TimelineClipRead:
    """P9-T012: rebind a clip to another asset/version."""
    return TimelineClipRead(**TimelineService(db).replace_clip_asset(clip_id, data.asset_id))


@router.post("/timelines/{timeline_id}/sequence-from-shots", response_model=TimelineRead)
def sequence_from_shots(timeline_id: str, db: Session = Depends(get_db)) -> TimelineRead:
    """One-click arrange: rebuild VIDEO + SUBTITLE tracks from the episode’s shots."""
    return _tl_read(TimelineService(db), TimelineService(db).sequence_from_shots(timeline_id))


@router.get("/timelines/{timeline_id}/preview")
def preview_timeline(timeline_id: str, db: Session = Depends(get_db)):
    """Non-render contact-sheet preview (JPEG). 204 when nothing to preview."""
    path = TimelineService(db).generate_preview(timeline_id)
    if path is None:
        from fastapi import Response

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/timelines/{timeline_id}/render", response_model=TimelineRenderRead, status_code=status.HTTP_202_ACCEPTED)
def render_timeline(timeline_id: str, db: Session = Depends(get_db)) -> TimelineRenderRead:
    """Queue an episode render: 202 + the queued type="render" generation."""
    service = TimelineService(db)
    timeline = TimelineService(db).get_timeline(timeline_id)
    generation = RenderService(db).create_render_generation(timeline_id)
    return TimelineRenderRead(
        generation_id=generation.id,
        timeline_id=timeline_id,
        episode_id=timeline["episode_id"],
        status=generation.status,
        message="Render queued.",
    )


@router.get("/episodes/{episode_id}/final-video", response_model=FinalVideoRead)
def get_final_video(episode_id: str, db: Session = Depends(get_db)) -> FinalVideoRead:
    """The latest rendered export (FINAL_VIDEO) of an episode; 404 when none."""
    data = RenderService(db).get_final_video(episode_id)
    if data is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Episode has no rendered final video yet.", {"episode_id": episode_id})
    return FinalVideoRead(**data)
