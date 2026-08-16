"""Continuity API (api-event-contract §142 P8; continuity-engine-design §176).

Phase-8 endpoints:

  GET  /api/v1/scenes/{scene_id}/continuity          → SceneContinuityRead
  GET  /api/v1/shots/{shot_id}/continuity-state      → ShotContinuityRead
  POST /api/v1/scenes/{scene_id}/continuity/recompute → ContinuityRecomputeRead
  GET  /api/v1/scenes/{scene_id}/continuity-warnings → open warnings for the scene
  POST /api/v1/continuity-warnings/{id}/acknowledge  → mark seen (stop re-flagging)
  GET  /api/v1/scenes/{scene_id}/transitions         → shot_transitions (structure)

Warnings returned by the scene aggregate come from the rule-engine snapshot stored
on each shot continuity row (shot_continuity_states.warnings_json, source=RULE),
merged with OPEN entries of the continuity_warnings table (rule + agent semantic,
P8-T018). The Agent check/fix entry points live in api/agents.py; this module only
surfaces persisted state and warnings.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.continuity import (
    ContinuityRecomputeRead,
    ContinuityWarningRead,
    SceneContinuityRead,
    ShotContinuityRead,
    TransitionRead,
)
from app.services.continuity_service import ContinuityService

router = APIRouter(tags=["continuity"])


@router.get(
    "/scenes/{scene_id}/continuity",
    response_model=SceneContinuityRead,
)
def get_scene_continuity(scene_id: str, db: Session = Depends(get_db)) -> SceneContinuityRead:
    data: dict[str, Any] = ContinuityService(db).get_scene_continuity(scene_id)
    # merge the parallel continuity_warnings table (P8-B) entries — read-only probe
    data["shots"] = _merge_shadow_warnings(db, scene_id, data["shots"])
    return SceneContinuityRead(**data)


@router.get(
    "/shots/{shot_id}/continuity-state",
    response_model=ShotContinuityRead,
)
def get_shot_continuity(shot_id: str, db: Session = Depends(get_db)) -> ShotContinuityRead:
    data: dict[str, Any] = ContinuityService(db).get_shot_continuity(shot_id)
    return ShotContinuityRead(**data)


@router.post(
    "/scenes/{scene_id}/continuity/recompute",
    response_model=ContinuityRecomputeRead,
)
def recompute_scene_continuity(scene_id: str, db: Session = Depends(get_db)) -> ContinuityRecomputeRead:
    """Manually trigger a dirty-range recompute (P8-T015) — recomputes the scene
    base + all shots and returns the new stable state hash."""
    svc = ContinuityService(db)
    svc.compute_scene_base(scene_id)
    recomputed, total = svc.compute_shot_states(scene_id, from_shot_id=None)
    shots = svc.get_scene_continuity(scene_id)["shots"]
    final_hash = shots[-1]["state_hash"] if shots else ""
    return ContinuityRecomputeRead(
        scene_id=scene_id,
        recomputed_from=None,
        recomputed_shots=recomputed,
        total_shots=total,
        state_hash=final_hash,
    )


def _merge_shadow_warnings(db: Session, scene_id: str, shots: list[dict]) -> list[dict]:
    """Merge OPEN continuity_warnings table entries into each shot's warnings.

    The continuity_warnings table (P8-T018) holds rule + agent semantic warnings;
    shot_continuity_states.warnings_json stays authoritative for rule snapshots.
    Wrapped so any schema drift degrades to the snapshot, never to a 500.
    """
    try:
        from sqlalchemy import text

        rows = db.execute(
            text(
                "SELECT shot_id, category, severity, message, id "
                "FROM continuity_warnings "
                "WHERE scene_id = :scene_id AND status = 'open'"
            ),
            {"scene_id": scene_id},
        ).mappings().all()
    except Exception:  # noqa: BLE001 — table not present yet or schema drift
        return shots
    if not rows:
        return shots
    by_shot: dict[str, list[dict]] = {}
    for row in rows:
        by_shot.setdefault(row["shot_id"], []).append({
            "code": row["category"] or "RULE",
            "category": row["category"] or "RULE",
            "severity": row["severity"] or "warning",
            "message": row["message"],
            "shot_id": row["shot_id"],
            "id": row["id"],
        })
    for shot in shots:
        extra = by_shot.get(shot["shot_id"], [])
        if not extra:
            continue
        existing_codes = {w.get("id") for w in shot.get("warnings", [])}
        for w in extra:
            if "id" in w and w["id"] not in existing_codes:
                shot["warnings"].append(w)
    return shots


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
