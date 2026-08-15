"""ReadModelService (P2-T011/T012/T013) — assembles aggregate read payloads.

These enrich the workspace-boot (bootstrap) and per-scene grid (storyboard)
endpoints with full navigation/detail shapes. The service owns all queries so the
Routers stay logic-free (AGENTS.md §3-red-line: Router → Service → Repository).
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Asset, Character, Episode, Project, Scene, Shot, ShotCharacter, ShotVisualSpec
from app.domain.project import ProjectRead
from app.domain.readmodels import (
    EpisodeTreeItem,
    InspectorCharacter,
    InspectorPromptVersionSummary,
    ProjectTreeRead,
    SceneEditorRead,
    SceneTreeItem,
    ShotEditorItem,
    ShotInspectorRead,
    ShotTreeItem,
)
from app.domain.shot_visual_spec import ShotVisualSpecRead
from app.repositories import ShotRepository
from app.services.prompt_service import PromptService
from app.services.scene_service import SceneService
from app.services.shot_service import ShotService


def _project_read(p: Project) -> ProjectRead:
    return ProjectRead(
        id=p.id,
        name=p.name,
        description=p.description,
        status=p.status,
        aspect_ratio=p.aspect_ratio,
        fps=p.fps,
        cover_url=f"/api/v1/projects/{p.id}/cover" if p.cover_path else None,
        revision=p.revision,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class ReadModelService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots_svc = ShotService(session)
        self.scenes_svc = SceneService(session)
        self.shot_repo = ShotRepository(session)
        self.prompts = PromptService(session)

    # ---------------------------------------------------------------- tree ----

    def project_tree(self, project_id: str) -> ProjectTreeRead:
        """P2-T011: project + episodes(scene_count) + scenes(shot_count) + shot summaries."""
        project = self.session.get(Project, project_id)
        if project is None or project.deleted_at:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        episodes = self.session.scalars(
            select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
        ).all()
        episode_ids = [e.id for e in episodes]
        if not episode_ids:
            return ProjectTreeRead(project=_project_read(project), episodes=[])

        scene_rows = self.session.execute(
            select(Scene)
            .where(Scene.episode_id.in_(episode_ids), Scene.deleted_at.is_(None))
            .order_by(Scene.episode_id, Scene.scene_number)
        ).scalars().all()
        scene_by_episode: dict[str, list[Scene]] = {}
        for sc in scene_rows:
            scene_by_episode.setdefault(sc.episode_id, []).append(sc)
        scene_ids = [sc.id for sc in scene_rows]

        shots: list[Shot] = []
        if scene_ids:
            shots = self.session.scalars(
                select(Shot).where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
            ).all()
        shots_by_scene: dict[str, list[Shot]] = {}
        for sh in shots:
            shots_by_scene.setdefault(sh.scene_id, []).append(sh)
        shot_ids = [sh.id for sh in shots]
        specs = self.shots_svc._specs_for(shot_ids)
        image_map, video_map = self._active_version_numbers(shot_ids)

        episodes_out: list[EpisodeTreeItem] = []
        for ep in episodes:
            scns = scene_by_episode.get(ep.id, [])
            scenes_out: list[SceneTreeItem] = []
            for sc in scns:
                sc_shots = shots_by_scene.get(sc.id, [])
                scenes_out.append(
                    SceneTreeItem(
                        id=sc.id,
                        scene_number=sc.scene_number,
                        name=sc.name,
                        shot_count=len(sc_shots),
                        shots=[
                            ShotTreeItem(
                                id=s.id,
                                shot_number=s.shot_number,
                                shot_type=(
                                    specs[s.id].shot_type
                                    if specs.get(s.id) and specs[s.id].shot_type is not None
                                    else s.shot_type
                                ),
                                status=s.status,
                                dirty_state=s.dirty_state,
                                revision=s.revision,
                                active_image_version=image_map.get(s.id),
                                active_video_version=video_map.get(s.id),
                                active_prompt_version_id=s.active_prompt_version_id,
                            )
                            for s in sc_shots
                        ],
                    )
                )
            episodes_out.append(
                EpisodeTreeItem(
                    id=ep.id,
                    episode_number=ep.episode_number,
                    title=ep.title,
                    scene_count=len(scns),
                    scenes=scenes_out,
                )
            )
        return ProjectTreeRead(project=_project_read(project), episodes=episodes_out)

    # ---------------------------------------------------------------- editor ----

    def scene_editor(self, scene_id: str) -> SceneEditorRead:
        """P2-T012: scene + shots with visual-spec summary + active versions + cast."""
        scene = self.scenes_svc.get_scene(scene_id)
        shots = self.session.scalars(
            select(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None)).order_by(Shot.shot_order)
        ).all()
        shot_ids = [s.id for s in shots]
        specs = self.shots_svc._specs_for(shot_ids)
        image_map, video_map = self._active_version_numbers(shot_ids)
        _, names = self.shots_svc._character_data(shot_ids)

        editor_shots: list[ShotEditorItem] = []
        for s in shots:
            spec = specs.get(s.id)
            editor_shots.append(
                ShotEditorItem(
                    id=s.id,
                    shot_number=s.shot_number,
                    shot_type=(spec.shot_type if spec and spec.shot_type is not None else s.shot_type),
                    status=s.status,
                    dirty_state=s.dirty_state,
                    duration=s.duration,
                    revision=s.revision,
                    title=None,
                    spec_summary={
                        "camera_angle": (spec.camera_angle if spec and spec.camera_angle is not None else s.camera_angle),
                        "camera_movement": (spec.camera_movement if spec and spec.camera_movement is not None else s.camera_movement),
                        "composition": spec.composition if spec else None,
                        "mood": (spec.mood if spec and spec.mood is not None else s.emotion),
                        "action": (spec.action if spec and spec.action is not None else s.action),
                        "lighting": spec.lighting if spec else None,
                        "location_id": spec.location_id if spec else None,
                    },
                    active_image_version=image_map.get(s.id),
                    active_video_version=video_map.get(s.id),
                    character_names=names.get(s.id, []),
                )
            )
        return SceneEditorRead(scene=scene, shots=editor_shots)

    # ---------------------------------------------------------------- inspector --

    def shot_inspector(self, shot_id: str) -> ShotInspectorRead:
        """P2-T013: full shot (spec-fallback) + visual spec + active versions +
        prompt version summary + cast with costume."""
        shot_svc = self.shots_svc
        shot = self.session.get(Shot, shot_id)
        if shot is None or shot.deleted_at:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        shot_svc._require_live_scene(shot)

        spec = shot_svc._specs_for([shot_id]).get(shot_id)
        read_spec = self._spec_read(shot, spec)
        shot_read = shot_svc.get_shot(shot_id)  # spec-fallback enabled in the read path

        image_map, video_map = self._active_version_numbers([shot_id])
        prompts = self._prompt_summaries(shot_id)
        characters = self._inspector_characters(shot_id)

        return ShotInspectorRead(
            shot=shot_read,
            visual_spec=read_spec,
            active_image_version=image_map.get(shot_id),
            active_video_version=video_map.get(shot_id),
            active_prompt_version_id=shot.active_prompt_version_id,
            prompts=prompts,
            characters=characters,
        )

    # ---------------------------------------------------------------- helpers --

    def _spec_read(self, shot: Shot, spec: ShotVisualSpec | None) -> ShotVisualSpecRead:
        """Full visual-spec read; when the spec row is absent, mirror the legacy
        shot columns so the inspector still surfaces the (legacy) visual fields."""
        if spec is None:
            return ShotVisualSpecRead(
                shot_id=shot.id,
                shot_type=shot.shot_type,
                camera_angle=shot.camera_angle,
                camera_movement=shot.camera_movement,
                mood=shot.emotion,
                action=shot.action,
                environment=shot.environment_description,
                present=False,
            )
        metadata: dict = {}
        if spec.metadata_json:
            try:
                parsed = json.loads(spec.metadata_json)
                if isinstance(parsed, dict):
                    metadata = parsed
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        return ShotVisualSpecRead(
            shot_id=spec.shot_id,
            shot_type=spec.shot_type,
            camera_angle=spec.camera_angle,
            camera_movement=spec.camera_movement,
            composition=spec.composition,
            location_id=spec.location_id,
            lighting=spec.lighting,
            mood=spec.mood,
            action=spec.action,
            facial_expression=spec.facial_expression,
            environment=spec.environment,
            style_instructions=spec.style_instructions,
            negative_instructions=spec.negative_instructions,
            metadata=metadata,
            present=True,
            created_at=spec.created_at,
            updated_at=spec.updated_at,
        )

    def _active_version_numbers(self, shot_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
        """Resolve shots.active_*_asset_id → asset.version_number (ADR-001)."""
        if not shot_ids:
            return {}, {}
        shots = self.session.scalars(
            select(Shot).where(Shot.id.in_(shot_ids))
        )
        asset_ids: set[str] = set()
        for s in shots:
            if s.active_image_asset_id:
                asset_ids.add(s.active_image_asset_id)
            if s.active_video_asset_id:
                asset_ids.add(s.active_video_asset_id)
        numbers: dict[str, int] = {}
        if asset_ids:
            for asset in self.session.scalars(select(Asset).where(Asset.id.in_(asset_ids))):
                if asset.version_number is not None:
                    numbers[asset.id] = asset.version_number
        image_map: dict[str, int] = {}
        video_map: dict[str, int] = {}
        for s in self.session.scalars(select(Shot).where(Shot.id.in_(shot_ids))):
            if s.active_image_asset_id and s.active_image_asset_id in numbers:
                image_map[s.id] = numbers[s.active_image_asset_id]
            if s.active_video_asset_id and s.active_video_asset_id in numbers:
                video_map[s.id] = numbers[s.active_video_asset_id]
        return image_map, video_map

    def _prompt_summaries(self, shot_id: str) -> dict[str, InspectorPromptVersionSummary]:
        """Active version number + count per prompt_type (ADR-002 authoritative active)."""
        out: dict[str, InspectorPromptVersionSummary] = {}
        for prompt in self.prompts.list_shot_prompts(shot_id):
            versions = self.prompts.list_versions(prompt.id)
            active = None
            if prompt.active_version_id:
                for v in versions:
                    if v.id == prompt.active_version_id:
                        active = v.version_number
                        break
            out[prompt.prompt_type] = InspectorPromptVersionSummary(
                active_version=active,
                version_count=len(versions),
                prompt_id=prompt.id,
            )
        return out

    def _inspector_characters(self, shot_id: str) -> list[InspectorCharacter]:
        """Cast of the shot with per-shot costume/role/pose from the link table."""
        links = self.session.scalars(
            select(ShotCharacter).where(ShotCharacter.shot_id == shot_id).order_by(ShotCharacter.created_at)
        ).all()
        if not links:
            return []
        character_ids = [link.character_id for link in links]
        characters = {
            c.id: c
            for c in self.session.scalars(select(Character).where(Character.id.in_(character_ids)))
        }
        out: list[InspectorCharacter] = []
        for link in links:
            char = characters.get(link.character_id)
            out.append(
                InspectorCharacter(
                    character_id=link.character_id,
                    name=char.name if char else link.character_id,
                    alias=char.alias if char else None,
                    master_version_id=char.master_version_id if char else None,
                    costume_id=link.costume_id or (char.default_costume_id if char else None),
                    role=link.role,
                    position=link.position,
                    pose=link.pose,
                )
            )
        return out
