"""Scene API (api-event-contract §16-18, mvp-spec §34/§36/§61)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm
from app.domain.scene import SceneCreate, SceneRead, SceneUpdateRequest
from app.domain.shot import StoryboardRead
from app.llm.gateway import LLMGateway
from app.operations.store import operation_store
from app.services import SceneService, ShotService
from app.services.script_service import ScriptService

router = APIRouter(tags=["scenes"])


@router.get("/episodes/{episode_id}/scenes", response_model=list[SceneRead])
def list_scenes(episode_id: str, db: Session = Depends(get_db)) -> list[SceneRead]:
    return SceneService(db).list_scenes(episode_id)


@router.post(
    "/episodes/{episode_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scene(episode_id: str, data: SceneCreate, db: Session = Depends(get_db)) -> SceneRead:
    return SceneService(db).create_scene(episode_id, data)


@router.get("/scenes/{scene_id}", response_model=SceneRead)
def get_scene(scene_id: str, db: Session = Depends(get_db)) -> SceneRead:
    return SceneService(db).get_scene(scene_id)


@router.patch("/scenes/{scene_id}", response_model=SceneRead)
def update_scene(
    scene_id: str,
    data: SceneUpdateRequest,
    db: Session = Depends(get_db),
) -> SceneRead:
    return SceneService(db).update_scene(scene_id, data.revision, data.patch)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_200_OK)
def delete_scene(scene_id: str, db: Session = Depends(get_db)) -> dict:
    """Soft delete (api-event-contract §89): returns {id, deleted: true}."""
    SceneService(db).delete_scene(scene_id)
    return {"id": scene_id, "deleted": True}


@router.get("/scenes/{scene_id}/storyboard", response_model=StoryboardRead)
def get_storyboard(scene_id: str, db: Session = Depends(get_db)) -> StoryboardRead:
    """Aggregate endpoint (api-event-contract §101): scene + shot summaries in one call."""
    return ShotService(db).get_storyboard(scene_id)


@router.post("/scenes/{scene_id}/generate-shots", status_code=status.HTTP_202_ACCEPTED)
async def generate_shots(
    scene_id: str,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_llm),
) -> dict:
    """202 + operation_id; the job persists ShotPlan[] when finished (mvp-spec §61)."""
    scene = SceneService(db).get_scene(scene_id)
    op = operation_store.create("scene_shot_planning", project_id=scene.episode_id)

    async def job() -> dict:
        from app.db.session import session_factory_provider

        async with operation_store.lock_for(f"shots:{scene_id}"):
            factory = session_factory_provider()
            with factory() as session:
                result = await ScriptService(session, llm).generate_shot_plans(scene_id)
                return result.model_dump()

    operation_store.start(op["id"], job)
    return {"operation_id": op["id"], "status": op["status"]}
