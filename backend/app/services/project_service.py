"""ProjectService (backend-architecture §11, mvp-spec §23, contract §103-104 bootstrap)."""

import json
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pathlib import Path

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Asset, Character, Costume, Episode, Generation, Location, Project, ProjectSetting, Scene, Shot, SourceDocument, Timeline
from app.db.models.columns import utcnow_iso
from app.events.bus import (
    EVENT_PROJECT_CREATED,
    EVENT_PROJECT_DELETED,
    EVENT_PROJECT_RESTORED,
    EVENT_PROJECT_UPDATED,
    StudioEvent,
    bus,
)
from app.domain.project import (
    EpisodeSummary,
    ProjectBootstrapRead,
    ProjectCreate,
    ProjectRead,
    ProjectSettingRead,
    ProjectSettingUpdate,
    ProjectUpdate,
    TrashItem,
)
from app.repositories import ProjectRepository
from app.services.character_service import CharacterService

PROJECT_UPDATE_FIELDS = (
    "name",
    "description",
    "status",
    "aspect_ratio",
    "fps",
    "default_language",
)

SETTING_FIELDS = frozenset(
    (
        "language",
        "default_llm_provider",
        "default_llm_model",
        "default_image_provider",
        "default_image_model",
        "default_video_provider",
        "default_video_model",
        "default_voice_provider",
        "default_voice_model",
        "default_image_workflow_id",
        "default_video_workflow_id",
    )
)
SETTING_INT_FIELDS = frozenset(
    (
        "auto_retry",
        "max_retry_count",
        "auto_save",
        "continuity_enabled",
        "auto_activate_new_generation",
    )
)


def _to_read(p: Project) -> ProjectRead:
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
        deleted_at=p.deleted_at,
    )


def _settings_to_read(s: ProjectSetting) -> ProjectSettingRead:
    extra: dict = {}
    if s.settings_json:
        try:
            parsed = json.loads(s.settings_json)
            if isinstance(parsed, dict):
                extra = parsed
        except (json.JSONDecodeError, TypeError):
            extra = {}
    return ProjectSettingRead(
        project_id=s.project_id,
        language=s.language,
        default_llm_provider=s.default_llm_provider,
        default_llm_model=s.default_llm_model,
        default_image_provider=s.default_image_provider,
        default_image_model=s.default_image_model,
        default_video_provider=s.default_video_provider,
        default_video_model=s.default_video_model,
        default_voice_provider=s.default_voice_provider,
        default_voice_model=s.default_voice_model,
        default_image_workflow_id=s.default_image_workflow_id,
        default_video_workflow_id=s.default_video_workflow_id,
        auto_retry=s.auto_retry,
        max_retry_count=s.max_retry_count,
        auto_save=s.auto_save,
        continuity_enabled=s.continuity_enabled,
        auto_activate_new_generation=s.auto_activate_new_generation,
        settings_json=extra,
        updated_at=s.updated_at,
    )


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProjectRepository(session)

    # --- project CRUD ---

    def create_project(self, data: ProjectCreate) -> ProjectRead:
        project = Project(
            name=data.name,
            description=data.description,
            status="draft",
            aspect_ratio=data.aspect_ratio,
            fps=data.fps,
            default_language=data.default_language,
            revision=1,
        )
        self.repo.add(project)
        self.session.flush()  # assign project.id (Python-side UUID default) before settings link
        # seed default settings row (database-schema-design §15) in the same tx
        self.session.add(ProjectSetting(project_id=project.id))
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_CREATED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
            )
        )
        return _to_read(project)

    def get_project(self, project_id: str) -> ProjectRead:
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return _to_read(project)

    def list_projects(self, include_deleted: bool = False) -> list[ProjectRead]:
        """Live projects by default; include_deleted=true appends soft-deleted
        rows (P2-E2-T01 project-level trash view) oldest-last by deleted_at."""
        live = [_to_read(p) for p in self.repo.list_ordered(order_by="created_at")]
        if not include_deleted:
            return live
        deleted = [
            _to_read(p)
            for p in self.session.scalars(
                select(Project).where(Project.deleted_at.is_not(None)).order_by(Project.deleted_at.desc())
            ).all()
        ]
        return live + deleted

    def update_project(self, project_id: str, revision: int, patch: ProjectUpdate) -> ProjectRead:
        """Optimistic concurrency (AGENTS.md §3.10): atomic conditional UPDATE.

        UPDATE projects SET revision = revision + 1 WHERE id = ? AND revision = ?
        Two stale writers cannot both win — the second one hits 0 rows and gets a 409.
        """
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        values: dict = {}
        changed: list[str] = []
        for field in PROJECT_UPDATE_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                values[field] = value
                changed.append(field)
        if not changed:
            return _to_read(project)

        values["updated_at"] = datetime.now(UTC).isoformat()
        stmt = (
            update(Project)
            .where(
                Project.id == project_id,
                Project.revision == revision,
                Project.deleted_at.is_(None),
            )
            .values(revision=Project.revision + 1, **values)
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            current = self.session.scalar(
                select(Project.revision).where(Project.id == project_id)
            )
            raise ConflictError(
                "Project was modified by another writer.",
                {
                    "project_id": project_id,
                    "expected_revision": revision,
                    "current_revision": current,
                },
            )
        self.session.commit()
        self.session.refresh(project)
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_UPDATED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
                payload={"revision": project.revision, "changed_fields": changed},
            )
        )
        return _to_read(project)

    def save_cover(self, project_id: str, filename: str, content: bytes) -> ProjectRead:
        """Persist an uploaded cover image under the project directory.

        DB stores only the relative path (portable layout, database-v0.1 §38-40).
        """
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        ext = Path(filename).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            raise ValidationError("Unsupported cover format.", {"filename": filename, "supported": [".png", ".jpg", ".jpeg", ".webp", ".gif"]})
        if len(content) > 10 * 1024 * 1024:
            raise ValidationError("Cover image too large (max 10 MB).", {"bytes": len(content)})

        cover_dir = settings.data_dir / "projects" / project_id
        cover_dir.mkdir(parents=True, exist_ok=True)
        # 固定文件名：cover<ext>，覆盖旧封面（每次上传替换）
        dest = cover_dir / f"cover{ext}"
        dest.write_bytes(content)
        project.cover_path = f"cover{ext}"
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_UPDATED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
                payload={"cover": True},
            )
        )
        return _to_read(project)

    def cover_path(self, project_id: str) -> Path | None:
        """Resolve the stored cover file, if any."""
        project = self.repo.get(project_id)
        if project is None or not project.cover_path:
            return None
        path = settings.data_dir / "projects" / project_id / project.cover_path
        return path if path.exists() else None

    def delete_project(self, project_id: str) -> None:
        """Soft-delete the project and cascade to its tree.

        Cascade set (same deleted_at timestamp, P2-E2-T01): episodes / scenes /
        shots / characters + locations / costumes / documents. Production records
        (generations / assets / versions / timelines / pipelines / snapshots) are
        NOT cascade-deleted — they stay as history and remain reachable through
        the restored project.
        """
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        deleted_at = utcnow_iso()  # ISO timestamp (soft delete, database-v0.1 §41)
        project.deleted_at = deleted_at

        # cascade soft delete (project tree disappears as a unit)
        episodes = self.session.execute(
            select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
        ).scalars().all()
        episode_ids = [ep.id for ep in episodes]
        scenes = self.session.execute(
            select(Scene).where(
                Scene.episode_id.in_(episode_ids) if episode_ids else Scene.id == "",
                Scene.deleted_at.is_(None),
            )
        ).scalars().all()
        scene_ids = [sc.id for sc in scenes]
        if scene_ids:
            shots = self.session.execute(
                select(Shot).where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
            ).scalars().all()
            for shot in shots:
                shot.deleted_at = deleted_at
        for scene in scenes:
            scene.deleted_at = deleted_at
        for episode in episodes:
            episode.deleted_at = deleted_at
        for character in self.session.execute(
            select(Character).where(Character.project_id == project_id, Character.deleted_at.is_(None))
        ).scalars().all():
            character.deleted_at = deleted_at
        # P2-E2-T01: project-scoped identity tables join the cascade so a deleted
        # project has no live children reachable by direct id (AC: 父删子不可见).
        for model in (Location, Costume, SourceDocument):
            for row in self.session.execute(
                select(model).where(model.project_id == project_id, model.deleted_at.is_(None))
            ).scalars().all():
                row.deleted_at = deleted_at

        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_DELETED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
            )
        )

    def restore_project(self, project_id: str) -> ProjectRead:
        """P2-E2-T01: restore a soft-deleted project + its cascade set.

        Only rows sharing the project's own deleted_at timestamp are revived —
        independently deleted children stay deleted. Already live → no-op.
        """
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        if project.deleted_at is None:
            return self.get_project(project_id)
        cascade_ts = project.deleted_at
        project.deleted_at = None
        for model, scope_field in (
            (Episode, Episode.project_id),
            (Character, Character.project_id),
            (Location, Location.project_id),
            (Costume, Costume.project_id),
            (SourceDocument, SourceDocument.project_id),
        ):
            for row in self.session.scalars(
                select(model).where(scope_field == project_id, model.deleted_at == cascade_ts)
            ).all():
                row.deleted_at = None
        # autoflush is OFF: flush revived rows before the dependent reads below.
        self.session.flush()
        episode_ids = [
            e.id
            for e in self.session.scalars(
                select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
            ).all()
        ]
        scenes = self.session.scalars(
            select(Scene).where(
                Scene.episode_id.in_(episode_ids) if episode_ids else Scene.id == "",
                Scene.deleted_at == cascade_ts,
            )
        ).all()
        for scene in scenes:
            scene.deleted_at = None
        self.session.flush()
        scene_ids = [s.id for s in scenes]
        if scene_ids:
            for shot in self.session.scalars(
                select(Shot).where(Shot.scene_id.in_(scene_ids), Shot.deleted_at == cascade_ts)
            ).all():
                shot.deleted_at = None
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_RESTORED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
            )
        )
        return self.get_project(project_id)

    def get_trash(self, project_id: str) -> list[TrashItem]:
        """P2-E2-T01: soft-deleted rows of the five restorable entities.

        Project itself is addressed by id (projects list only live rows); the
        trash covers its episode / scene / shot / character rows for review +
        per-row restore. Sorted by deleted_at descending (most recent first).
        Works for live AND soft-deleted projects (a deleted project's trash is
        how the user decides whether to restore it); unknown id → 404.
        """
        if self.session.get(Project, project_id) is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        items: list[TrashItem] = []
        for row in self.session.scalars(
            select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_not(None))
        ).all():
            items.append(TrashItem(
                entity_type="episode", id=row.id,
                name=row.title or f"EP{row.episode_number}",
                number=row.episode_number, parent_id=project_id,
                deleted_at=row.deleted_at,
            ))
        episode_ids = list(self.session.scalars(select(Episode.id).where(Episode.project_id == project_id)).all())
        for row in self.session.scalars(
            select(Scene).where(
                Scene.episode_id.in_(episode_ids) if episode_ids else Scene.id == "",
                Scene.deleted_at.is_not(None),
            )
        ).all():
            items.append(TrashItem(
                entity_type="scene", id=row.id,
                name=row.name or f"SC{row.scene_number}",
                number=row.scene_number, parent_id=row.episode_id,
                deleted_at=row.deleted_at,
            ))
        scene_ids = list(self.session.scalars(select(Scene.id).where(Scene.episode_id.in_(episode_ids) if episode_ids else Scene.id == "")).all())
        for row in self.session.scalars(
            select(Shot).where(
                Shot.scene_id.in_(scene_ids) if scene_ids else Shot.id == "",
                Shot.deleted_at.is_not(None),
            )
        ).all():
            items.append(TrashItem(
                entity_type="shot", id=row.id,
                name=f"SH{row.shot_number:03d}",
                number=row.shot_number, parent_id=row.scene_id,
                deleted_at=row.deleted_at,
            ))
        for row in self.session.scalars(
            select(Character).where(Character.project_id == project_id, Character.deleted_at.is_not(None))
        ).all():
            items.append(TrashItem(
                entity_type="character", id=row.id,
                name=row.name, number=None, parent_id=project_id,
                deleted_at=row.deleted_at,
            ))
        items.sort(key=lambda item: item.deleted_at or "", reverse=True)
        return items

    # --- ProjectSetting (database-schema-design §15) ---

    def _get_settings_row(self, project_id: str, *, create_if_missing: bool = False) -> ProjectSetting:
        """Return the project's settings row, optionally creating a default one."""
        row = self.session.get(ProjectSetting, project_id)
        if row is None and create_if_missing:
            self._require_project(project_id)
            row = ProjectSetting(project_id=project_id)
            self.session.add(row)
        return row

    def get_settings(self, project_id: str) -> ProjectSettingRead:
        self._require_project(project_id)
        row = self._get_settings_row(project_id)
        if row is None:
            # default settings (row may not exist for legacy projects created pre-migration)
            return ProjectSettingRead(
                project_id=project_id,
                updated_at=datetime.now(UTC).isoformat(),
            )
        return _settings_to_read(row)

    def update_settings(self, project_id: str, data: ProjectSettingUpdate) -> ProjectSettingRead:
        self._require_project(project_id)
        row = self._get_settings_row(project_id, create_if_missing=True)

        for field in SETTING_FIELDS:
            value = getattr(data, field)
            if value is not None:
                setattr(row, field, value)
        for field in SETTING_INT_FIELDS:
            value = getattr(data, field)
            if value is not None:
                setattr(row, field, value)

        # unknown keys from settings_json are preserved/merged
        if data.settings_json is not None:
            merged: dict = {}
            if row.settings_json:
                try:
                    existing = json.loads(row.settings_json)
                    if isinstance(existing, dict):
                        merged = existing
                except (json.JSONDecodeError, TypeError):
                    merged = {}
            merged.update(data.settings_json)
            row.settings_json = json.dumps(merged, ensure_ascii=False) if merged else None

        row.updated_at = datetime.now(UTC).isoformat()
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_UPDATED,
                entity_type="project",
                entity_id=project_id,
                project_id=project_id,
                payload={"settings": True},
            )
        )
        return _settings_to_read(row)

    def _require_project(self, project_id: str) -> Project:
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return project

    def bootstrap(self, project_id: str) -> ProjectBootstrapRead:
        """Workspace bootstrap (api-event-contract §103): summaries only — never full
        shots/prompts/assets (contract §104)."""
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        episodes = self.session.execute(
            select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
        ).scalars().all()
        episode_ids = [ep.id for ep in episodes]
        scene_counts: dict[str, int] = {}
        timeline_episode_ids: set[str] = set()
        final_video_episode_ids: set[str] = set()
        if episode_ids:
            rows = self.session.execute(
                select(Scene.episode_id, func.count(Scene.id))
                .where(Scene.episode_id.in_(episode_ids), Scene.deleted_at.is_(None))
                .group_by(Scene.episode_id)
            ).all()
            scene_counts = {episode_id: count for episode_id, count in rows}

            # P2 pipeline flags (contract §103): one grouped query per fact
            # instead of the frontend probing every episode endpoint.
            from app.services.render_service import final_video_version_group

            timeline_episode_ids = set(
                self.session.scalars(
                    select(Timeline.episode_id).where(Timeline.episode_id.in_(episode_ids))
                ).all()
            )
            group_to_episode = {final_video_version_group(eid): eid for eid in episode_ids}
            video_groups = self.session.execute(
                select(Asset.version_group_id)
                .where(Asset.version_group_id.in_(group_to_episode), Asset.deleted_at.is_(None))
                .group_by(Asset.version_group_id)
            ).scalars().all()
            final_video_episode_ids = {
                group_to_episode[group] for group in video_groups if group in group_to_episode
            }

        from app.agents.director.runner import active_run_count

        active_generations = self.session.scalar(
            select(func.count(Generation.id)).where(
                Generation.project_id == project_id,
                Generation.deleted_at.is_(None),
                Generation.status.in_(("queued", "running", "retrying")),
            )
        ) or 0

        from app.providers.registry import provider_status

        return ProjectBootstrapRead(
            project=_to_read(project),
            episodes=[
                EpisodeSummary(
                    id=ep.id,
                    episode_number=ep.episode_number,
                    title=ep.title,
                    scene_count=scene_counts.get(ep.id, 0),
                    has_timeline=ep.id in timeline_episode_ids,
                    has_final_video=ep.id in final_video_episode_ids,
                )
                for ep in episodes
            ],
            characters=CharacterService(self.session).list_summaries(project_id),
            providers=provider_status(),
            active_generations=active_generations,
            active_agent_runs=active_run_count(project_id),
        )
