"""Episode API (api-event-contract §13-15, §18; mvp-spec §33, §59)."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_script_llm
from app.domain.analysis import (
    AnalysisPreview,
    CharacterDecisionsRequest,
    CharacterDecisionsResult,
    SnapshotRead,
)
from app.domain.episode import (
    EpisodeCreate,
    EpisodeRead,
    EpisodeUpdateRequest,
)
from app.llm.gateway import LLMGateway
from app.operations.store import operation_store
from app.services import EpisodeService
from app.services.script_service import ScriptService

router = APIRouter(tags=["episodes"])

# Route ordering note: FastAPI matches in declaration order. Literal prefixes
# ("/episodes/{id}/analyze", "/episodes/{id}/scenes", ...) must be declared BEFORE
# the bare "/episodes/{episode_id}" GET/PATCH/DELETE below is a concern — but bare
# PATCH/DELETE only match the exact one-segment path, so no shadowing occurs.


@router.post(
    "/projects/{project_id}/episodes",
    response_model=EpisodeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_episode(project_id: str, data: EpisodeCreate, db: Session = Depends(get_db)) -> EpisodeRead:
    return EpisodeService(db).create_episode(project_id, data)


@router.get("/projects/{project_id}/episodes", response_model=list[EpisodeRead])
def list_episodes(project_id: str, db: Session = Depends(get_db)) -> list[EpisodeRead]:
    return EpisodeService(db).list_episodes(project_id)


@router.get("/episodes/{episode_id}", response_model=EpisodeRead)
def get_episode(episode_id: str, db: Session = Depends(get_db)) -> EpisodeRead:
    return EpisodeService(db).get_episode(episode_id)


@router.patch("/episodes/{episode_id}", response_model=EpisodeRead)
def update_episode(
    episode_id: str,
    data: EpisodeUpdateRequest,
    db: Session = Depends(get_db),
) -> EpisodeRead:
    return EpisodeService(db).update_episode(episode_id, data.revision, data.patch)


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_200_OK)
def delete_episode(episode_id: str, db: Session = Depends(get_db)) -> dict:
    """Soft-delete the episode and its scene/shot tree."""
    EpisodeService(db).delete_episode(episode_id)
    return {"id": episode_id, "deleted": True}


@router.post("/episodes/{episode_id}/restore", response_model=EpisodeRead)
def restore_episode(episode_id: str, db: Session = Depends(get_db)) -> EpisodeRead:
    """P2-E2-T01: restore a soft-deleted episode + its cascade set (409 when the
    parent project is deleted or a live sibling reuses the number)."""
    return EpisodeService(db).restore_episode(episode_id)


@router.post("/episodes/{episode_id}/analyze/preview", response_model=AnalysisPreview)
async def preview_analysis(
    episode_id: str,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_script_llm),
) -> AnalysisPreview:
    """P2-E1-T01: preview persists an immutable snapshot; confirm submits its id.

    The response envelope carries {snapshot_id, plans, source_hash, model} — the
    plans are EXACTLY what a later confirm writes (no second LLM call).
    """
    return await ScriptService(db, llm).preview_analysis(episode_id)


@router.post(
    "/episodes/{episode_id}/analyze/characters",
    response_model=CharacterDecisionsResult,
)
async def apply_character_decisions(
    episode_id: str,
    body: CharacterDecisionsRequest,
    db: Session = Depends(get_db),
) -> CharacterDecisionsResult:
    """P2-E1-T02: create / merge / skip reviewed candidates (per-item results).

    Router holds no business logic — ScriptService owns the snapshot-truth
    lookup, ownership checks, and per-item outcomes (always 200; failures are
    item-level, mirroring the batch逐项结果 pattern).
    """
    return await ScriptService(db, None).apply_character_decisions(episode_id, body)  # type: ignore[arg-type]


@router.get("/episodes/{episode_id}/analysis-snapshots/latest", response_model=SnapshotRead | None)
def get_latest_analysis_snapshot(
    episode_id: str,
    db: Session = Depends(get_db),
) -> SnapshotRead | None:
    """P2-E1-T01: newest snapshot (any status) — refresh rehydration + audit."""
    return ScriptService(db, None).get_latest_snapshot(episode_id)  # type: ignore[arg-type]


class AnalyzeRequest(BaseModel):
    """P2-E1-T01: confirm a reviewed preview snapshot (no LLM re-analysis).

    Omitted snapshot_id keeps the legacy behavior (analyze calls the LLM itself).
    """

    snapshot_id: str | None = None


@router.post(
    "/episodes/{episode_id}/analyze",
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze_episode(
    episode_id: str,
    body: AnalyzeRequest | None = None,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_script_llm),
) -> dict:
    """202 + operation_id; the job persists scenes when finished (contract §14-15).

    P2-E1-T01: with {snapshot_id} the job writes the REVIEWED snapshot plans
    (zero LLM calls, idempotent replay, 409 when the episode changed since
    preview). Without it, the legacy re-analysis path runs.
    """
    episode = EpisodeService(db).get_episode(episode_id)
    snapshot_id = (body.snapshot_id or "").strip() if body is not None else None
    op = operation_store.create("episode_analysis", project_id=episode.project_id)

    async def job() -> dict:
        from app.db.session import session_factory_provider

        async with operation_store.lock_for(f"analyze:{episode_id}"):
            factory = session_factory_provider()
            with factory() as session:
                service = ScriptService(session, llm)
                if snapshot_id:
                    result = await service.confirm_snapshot(episode_id, snapshot_id)
                else:
                    result = await service.analyze_episode(episode_id)
                return result.model_dump()

    operation_store.start(op["id"], job)
    return {"operation_id": op["id"], "status": op["status"]}
