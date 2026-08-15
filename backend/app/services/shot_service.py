"""ShotService — the core production service (backend-architecture §14, mvp-spec §26).

Rules:
- update_shot() increments revision (optimistic concurrency, api-event-contract §21/§88).
- All mutations publish domain events AFTER commit (red line: commit then publish).
- No provider/model knowledge here (red line: ShotService never knows concrete models).
- Character assignment lives in the shot_characters link table (database-v0.1 §11);
  character_ids are validated against the owning project (cross-project refs are rejected).
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Character, Episode, Scene, Shot, ShotCharacter, ShotVisualSpec
from app.domain.scene import SceneSummary
from app.domain.shot import (
    ShotCreate,
    ShotRead,
    ShotSummary,
    ShotUpdate,
    StoryboardRead,
)
from app.events.bus import (
    EVENT_SHOT_CREATED,
    EVENT_SHOT_DELETED,
    EVENT_SHOT_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import SceneRepository, ShotCharacterRepository, ShotRepository

DIRTY_FIELDS = {
    "image_prompt",
    "negative_prompt",
    "shot_type",
    "camera_angle",
    "camera_movement",
    "lens",
    "action",
    "emotion",
    "duration",
    "character_ids",
}


def _to_read(
    s: Shot,
    character_ids: list[str] | None = None,
    spec: ShotVisualSpec | None = None,
) -> ShotRead:
    """Build the shot DTO. P2-T005: prefer the ShotVisualSpec fields and fall back
    to the deprecated inline shot columns when the spec/mapping field is missing,
    so legacy rows created before the spec migration stay fully readable."""
    mapped = spec.mapped_read_dict() if spec is not None else {}
    return ShotRead(
        id=s.id,
        scene_id=s.scene_id,
        shot_number=s.shot_number,
        shot_order=s.shot_order,
        shot_type=_spec_or_legacy(mapped, "shot_type", s.shot_type),
        camera_angle=_spec_or_legacy(mapped, "camera_angle", s.camera_angle),
        camera_movement=_spec_or_legacy(mapped, "camera_movement", s.camera_movement),
        lens=s.lens,
        duration=s.duration,
        action=_spec_or_legacy(mapped, "action", s.action),
        emotion=_spec_or_legacy(mapped, "emotion", s.emotion),
        dialogue=s.dialogue,
        image_prompt=s.image_prompt,
        character_ids=character_ids or [],
        status=s.status,
        dirty_state=s.dirty_state,
        revision=s.revision,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_summary(
    s: Shot,
    character_names: list[str] | None = None,
    spec: ShotVisualSpec | None = None,
) -> ShotSummary:
    mapped = spec.mapped_read_dict() if spec is not None else {}
    return ShotSummary(
        id=s.id,
        shot_number=s.shot_number,
        shot_type=_spec_or_legacy(mapped, "shot_type", s.shot_type),
        duration=s.duration,
        status=s.status,
        dirty_state=s.dirty_state,
        thumbnail_url=None,  # resolved per-shot in get_storyboard (needs DB lookups)
        character_names=character_names or [],
    )


def _spec_or_legacy(mapped: dict, key: str, legacy: object) -> object | None:
    """P2-T005 read preference: use the formal spec value when present (neither a
    missing spec row nor a NULL spec field), otherwise fall back to the legacy
    inline shot column."""
    value = mapped.get(key)
    return value if value is not None else legacy


class ShotService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ShotRepository(session)
        self.scenes = SceneRepository(session)
        self.links = ShotCharacterRepository(session)

    def create_shot(self, scene_id: str, data: ShotCreate) -> ShotRead:
        """Create ONE shot; commits and publishes shot.created (manual/API path)."""
        shot = self.create_shots(scene_id, [data])[0]
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_CREATED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=self._project_id_of(shot),
            )
        )
        ids, _ = self._character_data([shot.id])
        spec = self._specs_for([shot.id]).get(shot.id)
        return _to_read(shot, ids.get(shot.id, []), spec)

    def create_shots(
        self,
        scene_id: str,
        datas: list[ShotCreate],
        analysis_key: str | None = None,
    ) -> list[Shot]:
        """Batch create WITHOUT committing (P1-E1-T01: caller owns the transaction).

        All-or-nothing: any error raises before commit; the caller rolls back and
        nothing is persisted. analysis_key marks AI-created shots (replace policy).
        """
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        created: list[Shot] = []
        for data in datas:
            shot_number = data.shot_number or self.repo.next_shot_number(scene_id)
            shot = Shot(
                scene_id=scene_id,
                shot_number=shot_number,
                shot_order=shot_number,
                shot_type=data.shot_type,
                camera_angle=data.camera_angle,
                camera_movement=data.camera_movement,
                lens=data.lens,
                duration=data.duration,
                action=data.action,
                emotion=data.emotion,
                dialogue=data.dialogue,
                image_prompt=data.image_prompt,
                analysis_key=analysis_key,
                status="draft",
                dirty_state="clean",
                revision=1,
            )
            self.repo.add(shot)
            self.session.flush()  # assign shot.id before link rows reference it (autoflush=False)
            self._upsert_spec(shot)  # P2-T005: same-transaction write-through
            if data.image_prompt:
                # ADR-002: inline prompt at creation is backed by a v1 prompt version
                from app.services.prompt_service import PromptService

                PromptService(self.session).create_version(
                    project_id=self._project_id_of(shot) or "",
                    target_type="SHOT",
                    target_id=shot.id,
                    prompt_type="SHOT_IMAGE",
                    positive=data.image_prompt,
                    negative=shot.negative_prompt,
                    generated_by="user",
                    commit=False,
                )
            assignments = self._resolve_assignments(data, scene)
            if assignments:
                self._replace_characters(shot, assignments)
            created.append(shot)
        return created

    def soft_delete_shots(self, scene_ids: list[str]) -> None:
        """Soft-delete ALL live shots of the given scenes (no commit — caller owns the transaction)."""
        if not scene_ids:
            return
        shots = self.session.scalars(
            select(Shot).where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
        )
        for shot in shots:
            self.repo.delete(shot)

    def soft_delete_ai_shots(self, scene_id: str) -> None:
        """Soft-delete AI-created shots of one scene (analysis_key IS NOT NULL);
        manual shots are preserved. No commit — caller owns the transaction."""
        shots = self.session.scalars(
            select(Shot).where(
                Shot.scene_id == scene_id,
                Shot.analysis_key.isnot(None),
                Shot.deleted_at.is_(None),
            )
        )
        for shot in shots:
            self.repo.delete(shot)

    def list_shots_with_key(self, scene_id: str, analysis_key: str) -> list[Shot]:
        """Live shots of a scene created by a specific storyboard key (idempotency check)."""
        return self.repo.list_ordered(
            order_by="shot_order", scene_id=scene_id, analysis_key=analysis_key
        )

    def get_shot(self, shot_id: str) -> ShotRead:
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        self._require_live_scene(shot)  # P1-E1-T02: hidden when the parent scene is soft-deleted
        ids, _ = self._character_data([shot_id])
        spec = self._specs_for([shot_id]).get(shot_id)
        return _to_read(shot, ids.get(shot_id, []), spec)

    def list_shots(self, scene_id: str) -> list[ShotRead]:
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        shots = self.repo.list_for_scene(scene_id)
        ids, _ = self._character_data([s.id for s in shots])
        specs = self._specs_for([s.id for s in shots])
        return [_to_read(s, ids.get(s.id, []), specs.get(s.id)) for s in shots]

    def update_shot(
        self,
        shot_id: str,
        revision: int,
        patch: ShotUpdate,
        source: str = "user",
        run_id: str | None = None,
    ) -> ShotRead:
        """Optimistic concurrency update (P1-E1-T02: ATOMIC conditional update).

        The revision guard is enforced by the database:
            UPDATE shots SET revision = revision + 1 WHERE id = ? AND revision = ?
        Two writers that both read revision N cannot both win — the second one's
        UPDATE matches 0 rows and gets a 409, instead of silently overwriting.

        P1-E3-T02: source ("user" | "agent") and run_id are recorded in the
        shot.updated event payload so the audit trail can distinguish origins.
        """
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        self._require_live_scene(shot)

        values: dict = {}
        changed: list[str] = []
        # ADR-002: prompt edits create a new PromptVersion (write-through cache
        # syncs shot.image_prompt/negative_prompt + active pointer inside the service).
        prompt_change = patch.image_prompt is not None
        if prompt_change:
            from app.services.prompt_service import PromptService

            PromptService(self.session).create_version(
                project_id=self._project_id_of(shot) or "",
                target_type="SHOT",
                target_id=shot.id,
                prompt_type="SHOT_IMAGE",
                positive=patch.image_prompt,
                negative=shot.negative_prompt,
                generated_by=source,
                commit=False,
            )
            changed.append("image_prompt")
        for field in (
            "shot_type",
            "camera_angle",
            "camera_movement",
            "lens",
            "duration",
            "action",
            "emotion",
            "dialogue",
            "status",
            "dirty_state",
        ):
            value = getattr(patch, field)
            if value is not None:
                values[field] = value
                changed.append(field)
        character_change = patch.character_ids is not None or patch.characters is not None
        assignments: list[dict] = []
        if character_change:
            scene = self.session.get(Scene, shot.scene_id)
            assignments = self._resolve_assignments(patch, scene)
            changed.append("character_ids")

        if not values and not character_change and not prompt_change:
            ids, _ = self._character_data([shot_id])
            spec = self._specs_for([shot_id]).get(shot_id)
            return _to_read(shot, ids.get(shot_id, []), spec)

        if any(f in DIRTY_FIELDS for f in changed):
            values["dirty_state"] = "dirty_image"
        from datetime import UTC, datetime

        values["updated_at"] = datetime.now(UTC).isoformat()

        # P1-E1-T02: atomic revision guard — one conditional UPDATE, no read-check-write.
        stmt = (
            update(Shot)
            .where(Shot.id == shot_id, Shot.revision == revision, Shot.deleted_at.is_(None))
            .values(revision=Shot.revision + 1, **values)
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            current = self.session.scalar(select(Shot.revision).where(Shot.id == shot_id))
            raise ConflictError(
                "Shot was modified by another writer.",
                {
                    "shot_id": shot_id,
                    "expected_revision": revision,
                    "current_revision": current,
                },
            )
        if character_change:
            self._replace_characters(shot, assignments)
        # Persist any pending ORM-side changes (prompt write-through cache, character
        # links) BEFORE refreshing, so the reload sees the conditional-UPDATE columns
        # AND the prompt-cache columns at their new values — one transaction (P2-T005).
        self.session.flush()
        self.session.refresh(shot)
        self._upsert_spec(shot)  # P2-T005: same-transaction write-through
        self.session.commit()

        if changed:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_SHOT_UPDATED,
                    entity_type="shot",
                    entity_id=shot.id,
                    project_id=self._project_id_of(shot),
                    payload={
                        "revision": shot.revision,
                        "changed_fields": changed,
                        "source": source,
                        "run_id": run_id,
                    },
                )
            )
        ids, _ = self._character_data([shot_id])
        spec = self._specs_for([shot_id]).get(shot_id)
        return _to_read(shot, ids.get(shot_id, []), spec)

    def delete_shot(self, shot_id: str) -> None:
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        self._require_live_scene(shot)
        self.repo.delete(shot)  # soft delete
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_DELETED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=self._project_id_of(shot),
            )
        )

    def reorder_shots(self, scene_id: str, ordered_ids: list[str]) -> list[ShotRead]:
        """Safe reorder (P1-E1-T02): the list must contain EXACTLY the scene's live
        shots — partial, duplicate or cross-scene ids are rejected before any write;
        numbering is two-phase inside one transaction to avoid unique-order conflicts."""
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        shots = {s.id: s for s in self.repo.list_for_scene(scene_id)}
        if len(ordered_ids) != len(set(ordered_ids)):
            raise ValidationError(
                "Reorder list contains duplicate shot ids.",
                {"scene_id": scene_id},
            )
        if set(ordered_ids) != set(shots):
            missing = sorted(set(shots) - set(ordered_ids))
            unknown = sorted(set(ordered_ids) - set(shots))
            raise ValidationError(
                "Reorder must contain exactly the scene's shots (no partial or cross-scene ids).",
                {"scene_id": scene_id, "missing": missing, "unknown": unknown},
            )
        # phase 1: move every shot out of the way (unique shot_number AND shot_order
        # indexes cover live rows); phase 2: assign the final order — one transaction.
        offset = len(shots) + 1
        for shot in shots.values():
            shot.shot_order += offset
            shot.shot_number += offset
        self.session.flush()
        for index, shot_id in enumerate(ordered_ids, start=1):
            shot = shots[shot_id]
            shot.shot_order = index
            shot.shot_number = index
        self.session.commit()
        ids, _ = self._character_data(list(shots))
        live = self.repo.list_for_scene(scene_id)
        specs = self._specs_for([s.id for s in live])
        return [_to_read(s, ids.get(s.id, []), specs.get(s.id)) for s in live]

    def get_storyboard(self, scene_id: str) -> StoryboardRead:
        """Aggregate endpoint payload (api-event-contract §101-102) — avoids N+1 on the grid."""
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        shots = self.repo.list_for_scene(scene_id)
        thumbnails = self._thumbnail_urls(shots)
        _, names = self._character_data([s.id for s in shots])
        specs = self._specs_for([s.id for s in shots])
        summaries = []
        for s in shots:
            summary = _to_summary(s, names.get(s.id, []), specs.get(s.id))
            summary.thumbnail_url = thumbnails.get(s.id)
            summaries.append(summary)
        return StoryboardRead(
            scene=SceneSummary(id=scene.id, scene_number=scene.scene_number, name=scene.name),
            shots=summaries,
        )

    # --- ShotVisualSpec (P2-T005: formalized spec, 1:1 with shots) ---

    def _specs_for(self, shot_ids: list[str]) -> dict[str, ShotVisualSpec]:
        """shot_id → ShotVisualSpec, one query (SELECT ... WHERE shot_id IN (...))."""
        if not shot_ids:
            return {}
        specs = self.session.scalars(
            select(ShotVisualSpec).where(ShotVisualSpec.shot_id.in_(shot_ids))
        )
        return {spec.shot_id: spec for spec in specs}

    def _upsert_spec(self, shot: Shot) -> None:
        """Write-through the formal ShotVisualSpec row from the shot's live framing
        fields + its scene's world/staging, in the SAME transaction (P2-T005).

        Fields that have no legacy inline shot column (composition, facial_expression,
        style_instructions, negative_instructions) are left untouched by this sync so
        an external writer can fill them later; the spec keeps whatever it already has.
        """
        scene = self.session.get(Scene, shot.scene_id)
        spec = self.session.get(ShotVisualSpec, shot.id)
        if spec is None:
            spec = ShotVisualSpec(shot_id=shot.id)
            self.session.add(spec)
        spec.shot_type = shot.shot_type
        spec.camera_angle = shot.camera_angle
        spec.camera_movement = shot.camera_movement
        spec.action = shot.action
        spec.mood = shot.emotion  # spec.mood ↔ shot.emotion (legacy)
        spec.environment = shot.environment_description
        spec.location_id = scene.location_id if scene else None
        spec.lighting = scene.lighting if scene else None

    # --- character assignment (database-v0.1 §11) ---

    def _validate_characters(self, character_ids: list[str], scene: Scene | None) -> None:
        """Characters must exist (not deleted) and belong to the shot's project."""
        from app.core.errors import ValidationError

        if not character_ids:
            return
        # P1-E1-T02: duplicates would violate the (shot_id, character_id) unique index
        duplicate_ids = [cid for cid in set(character_ids) if character_ids.count(cid) > 1]
        if duplicate_ids:
            raise ValidationError(
                "Character ids must be unique.",
                {"character_ids": duplicate_ids},
            )
        characters = {
            c.id: c
            for c in self.session.scalars(
                select(Character).where(Character.id.in_(character_ids))
            )
        }
        unknown = [cid for cid in character_ids if cid not in characters]
        if unknown:
            raise NotFoundError("Character does not exist.", {"character_ids": unknown})
        project_id = self._project_id_of(scene) if scene else None
        foreign = [cid for cid in character_ids if characters[cid].project_id != project_id]
        if foreign:
            raise ValidationError(
                "Character belongs to another project.",
                {"character_ids": foreign, "project_id": project_id},
            )

    def _resolve_assignments(
        self, data, scene: Scene | None
    ) -> list[dict]:
        """Backward-compatible resolution of shot character assignment.

        If the P2-T010 'characters' list (character_id + optional costume_id) is present
        it supersedes the plain 'character_ids' list. Returns a list of dicts
        {character_id, costume_id}. Character projection ownership is validated; any
        referenced costume is validated for existence + same-project membership.
        """
        from app.core.errors import ValidationError

        characters = getattr(data, "characters", None)
        character_ids = getattr(data, "character_ids", None) or []
        if characters is not None:
            character_ids = [a.character_id for a in characters]
        self._validate_characters(character_ids, scene)

        project_id = self._project_id_of(scene) if scene else None
        costume_ids = [a.costume_id for a in characters if a.costume_id] if characters else []
        if costume_ids:
            from app.db.models import Costume

            costumes = {
                c.id: c
                for c in self.session.scalars(
                    select(Costume).where(Costume.id.in_(costume_ids), Costume.deleted_at.is_(None))
                )
            }
            unknown_costumes = [cid for cid in costume_ids if cid not in costumes]
            if unknown_costumes:
                raise NotFoundError("Costume does not exist.", {"costume_ids": unknown_costumes})
            foreign = [cid for cid in costume_ids if costumes[cid].project_id != project_id]
            if foreign:
                raise ValidationError(
                    "Costume belongs to another project.",
                    {"costume_ids": foreign, "project_id": project_id},
                )

        if characters is not None:
            # duplicate character_id would violate the (shot_id, character_id) unique index
            seen: set[str] = set()
            for a in characters:
                if a.character_id in seen:
                    raise ValidationError(
                        "Character ids must be unique.",
                        {"character_ids": [a.character_id]},
                    )
                seen.add(a.character_id)
            # honor explicit costume order (matches characters order)
            return [
                {"character_id": a.character_id, "costume_id": a.costume_id}
                for a in characters
            ]
        return [{"character_id": cid, "costume_id": None} for cid in character_ids]

    def _replace_characters(self, shot: Shot, assignments: list[dict]) -> None:
        """Replace the shot's character links (ephemeral link rows, no version history).

        assignments: list of {character_id, costume_id}. P1-E1-T02: old links are
        hard-deleted and flushed BEFORE inserting new ones — the (shot_id, character_id)
        unique index would otherwise reject same-pair re-adds in the same flush
        (SQLAlchemy emits INSERTs before DELETEs). P2-T010 records optional costume_id."""
        self.links.delete_for_shot(shot.id)
        self.session.flush()
        for assignment in assignments:
            self.session.add(
                ShotCharacter(
                    shot_id=shot.id,
                    character_id=assignment["character_id"],
                    costume_id=assignment.get("costume_id"),
                )
            )

    def _character_data(self, shot_ids: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """(shot_id → character_ids, shot_id → character_names) — soft-deleted characters
        keep their name as history; links are ordered by insertion."""
        if not shot_ids:
            return {}, {}
        links = self.links.list_for_shots(shot_ids)
        if not links:
            return {}, {}
        character_ids = {link.character_id for link in links}
        characters = {
            c.id: c.name
            for c in self.session.scalars(select(Character).where(Character.id.in_(character_ids)))
        }
        ids_map: dict[str, list[str]] = {}
        names_map: dict[str, list[str]] = {}
        for link in links:
            ids_map.setdefault(link.shot_id, []).append(link.character_id)
            names_map.setdefault(link.shot_id, []).append(
                characters.get(link.character_id, link.character_id)
            )
        return ids_map, names_map

    def _thumbnail_urls(self, shots: list[Shot]) -> dict[str, str | None]:
        """Map shot_id → thumbnail URL via the shot's active image asset (ADR-001)."""
        from app.db.models import Asset

        asset_ids = [s.active_image_asset_id for s in shots if s.active_image_asset_id]
        if not asset_ids:
            return {s.id: None for s in shots}
        self.session.scalars(select(Asset).where(Asset.id.in_(asset_ids)))  # warm identity map (P1-E2-T01 lint cleanup)
        return {
            s.id: (f"/api/v1/assets/{s.active_image_asset_id}/thumbnail"
                   if s.active_image_asset_id else None)
            for s in shots
        }

    def _require_live_scene(self, shot: Shot) -> None:
        """P1-E1-T02: children of a soft-deleted parent are hidden (read AND write)."""
        scene = self.scenes.get(shot.scene_id)
        if scene is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot.id})

    def _project_id_of(self, obj: Shot | Scene) -> str | None:
        if isinstance(obj, Shot):
            scene = self.session.get(Scene, obj.scene_id)
        else:
            scene = obj
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
