"""Read Model API (P2-T011/T012/T013): tree / editor / inspector.

Formalized aggregate read shapes that complement bootstrap (workspace boot
summaries, contract §103-104) and storyboard (per-scene grid, §101-102).
All payload assembly lives in ReadModelService — Router stays logic-free.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.readmodels import ProjectTreeRead, SceneEditorRead, ShotInspectorRead
from app.services import ReadModelService

router = APIRouter(tags=["read-models"])


@router.get("/projects/{project_id}/tree", response_model=ProjectTreeRead)
def project_tree(project_id: str, db: Session = Depends(get_db)) -> ProjectTreeRead:
    """P2-T011: project + episodes(scene_count) + scenes(shot_count) + shot summaries."""
    return ReadModelService(db).project_tree(project_id)


@router.get("/scenes/{scene_id}/editor", response_model=SceneEditorRead)
def scene_editor(scene_id: str, db: Session = Depends(get_db)) -> SceneEditorRead:
    """P2-T012: scene + shots with visual-spec summary + active versions + cast."""
    return ReadModelService(db).scene_editor(scene_id)


@router.get("/shots/{shot_id}/inspector", response_model=ShotInspectorRead)
def shot_inspector(shot_id: str, db: Session = Depends(get_db)) -> ShotInspectorRead:
    """P2-T013: full shot + visual spec + active versions + prompt summary + cast."""
    return ReadModelService(db).shot_inspector(shot_id)
