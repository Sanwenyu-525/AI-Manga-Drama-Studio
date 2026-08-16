"""Continuity warnings + transitions API (P8-T018/T019/T024..T026; api-event-contract §142).

- GET    /scenes/{id}/continuity-warnings    → open warnings for the scene
- POST   /continuity-warnings/{id}/acknowledge → mark seen (stop re-flagging)
- GET    /scenes/{id}/transitions            → shot_transitions for the scene (structure)

These are Query/Command endpoints backing the frontend's Scene Warning + Shot
Inspector continuity UI (P8-T020). The Agent check/fix entry points live in
api/agents.py; this module only surfaces persisted warnings.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.continuity import ContinuityWarningRead, TransitionRead
from app.services.continuity_service import ContinuityService

router = APIRouter(tags=["continuity"])


@router.get("/scenes/{scene_id}/continuity-warnings", response_model=list[ContinuityWarningRead])
def list_scene_continuity_warnings(scene_id: str, db: Session = Depends(get_db)) -> list[ContinuityWarningRead]:
    """Open (open + acknowledged, i.e. not-fixed) warnings for a scene, newest first."""
    return ContinuityService(db).list_open_warnings(scene_id)


@router.post("/continuity-warnings/{warning_id}/acknowledge", response_model=ContinuityWarningRead)
def acknowledge_warning(warning_id: str, db: Session = Depends(get_db)) -> ContinuityWarningRead:
    """Mark a warning acknowledged (read/seen) so it stops being repeatedly flagged."""
    return ContinuityService(db).acknowledge(warning_id)


@router.get("/scenes/{scene_id}/transitions", response_model=list[TransitionRead])
def list_scene_transitions(scene_id: str, db: Session = Depends(get_db)) -> list[TransitionRead]:
    """List shot_transitions for a scene (P8-T024..T026 structure only)."""
    return ContinuityService(db).list_transitions(scene_id)
