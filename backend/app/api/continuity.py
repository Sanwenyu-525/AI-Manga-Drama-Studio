"""Continuity API (api-event-contract §142 P8; continuity-engine-design §176).

Three Phase-8 endpoints for the Continuity Engine view:

  GET  /api/v1/scenes/{scene_id}/continuity         → SceneContinuityRead
  GET  /api/v1/shots/{shot_id}/continuity-state     → ShotContinuityRead
  POST /api/v1/scenes/{scene_id}/continuity/recompute → ContinuityRecomputeRead

Warnings returned here come from the rule-engine snapshot stored on each shot
continuity row (shot_continuity_states.warnings_json, source=RULE). When the
parallel continuation_warnings table (P8-continuity-agent) lands, the scene
aggregation also merges its OPEN entries for the scene; until then warnings_json
is authoritative.
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.continuity import (
    ContinuityRecomputeRead,
    SceneContinuityRead,
    ShotContinuityRead,
)
from app.services import ContinuityService

router = APIRouter(tags=["continuity"])


@router.get(
    "/scenes/{scene_id}/continuity",
    response_model=SceneContinuityRead,
)
def get_scene_continuity(scene_id: str, db: Session = Depends(get_db)) -> SceneContinuityRead:
    data: dict[str, Any] = ContinuityService(db).get_scene_continuity(scene_id)
    # merge the parallel continuity_warnings table (P8-B) if present — read-only probe
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
    """Compatibility with the parallel continuation_warnings table (P8-continuity-agent).

    If that table exists, append its OPEN entries for this scene's shots to each shot's
    warnings (deduping by warning id). If it does NOT exist (P8-B not yet merged), the
    snapshot warnings_json stays authoritative and this is a no-op. Wrapped so any schema
    drift degrades to the snapshot, never to a 500."""
    try:
        from sqlalchemy import text

        rows = db.execute(
            text(
                "SELECT shot_id, rule_code, category, severity, message, id "
                "FROM continuation_warnings "
                "WHERE scene_id = :scene_id AND status = 'OPEN'"
            ),
            {"scene_id": scene_id},
        ).mappings().all()
    except Exception:  # noqa: BLE001 — table not present yet (P8-B) or schema drift
        return shots
    if not rows:
        return shots
    by_shot: dict[str, list[dict]] = {}
    for row in rows:
        by_shot.setdefault(row["shot_id"], []).append({
            "code": row["rule_code"],
            "category": row["category"] or "RULE",
            "severity": row["severity"] or "WARNING",
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
