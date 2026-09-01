"""GenerationService (backend-architecture §16, mvp-spec §68) — the boundary between
Studio and the AI generation world.

- create_generation: persist record (status=queued) + enqueue to the worker.
- retry_generation: creates a NEW record (retry_of=old) — never overwrites history (red line).
- cancel_generation / complete / fail: state transitions + events.
"""

from __future__ import annotations

import json
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Generation, GenerationInput, Shot
from app.domain.generation import GenerationCreate
from app.events.bus import (
    EVENT_GENERATION_CANCELLED,
    EVENT_GENERATION_CREATED,
    EVENT_GENERATION_QUEUED,
    StudioEvent,
    bus,
)
from app.repositories import ShotRepository

logger = get_logger("generations")

TERMINAL = ("completed", "failed", "cancelled")


class GenerationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotRepository(session)

    def create_generation(self, shot_id: str, data: GenerationCreate, *, run_id: str | None = None) -> Generation:
        shot = self.shots.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        # project id via shot chain
        project_id = self._project_id_of(shot)
        if project_id is None:
            raise NotFoundError("Shot has no project.", {"shot_id": shot_id})

        # P1-E2-T01: fail fast BEFORE queuing — canonical provider id, supported
        # media type, known workflow. generation.provider will equal the
        # implementation the worker actually runs.
        if data.type not in ("image", "video"):
            raise ValidationError(
                "Unsupported generation type.",
                {"type": data.type, "supported": ["image", "video"]},
            )
        # Idempotency guard: one expensive generation per shot+type at a time.
        # A double-click must not queue two identical costly tasks (409 → UI keeps
        # the in-flight one). Completed/failed rows don't block regeneration.
        in_flight = self.session.scalar(
            select(func.count())
            .select_from(Generation)
            .where(
                Generation.shot_id == shot_id,
                Generation.type == data.type,
                Generation.deleted_at.is_(None),
                Generation.status.in_(("queued", "running", "retrying", "cancelling")),
            )
        )
        if in_flight:
            raise ConflictError(
                "A generation of this type is already queued or running for this shot.",
                {"shot_id": shot_id, "type": data.type},
            )
        resolved_workflow_id: str | None = None
        if data.type == "video":
            # 视频直连云端任务 API，不经过 workflow 模板。
            from app.providers.registry import get_video_provider
            from app.services.image_settings_service import get_video_config

            provider = data.provider or get_video_config()["provider"]
            get_video_provider(provider)  # unknown provider → ValidationError (422)
        else:
            from app.providers.registry import get_image_provider
            from app.services.image_settings_service import get_image_config

            provider = data.provider or get_image_config()["provider"]
            get_image_provider(provider)  # unknown provider → ValidationError (422)
            # P4-T007: explicit workflow_id keeps the strict 422 preflight; an omitted
            # one is resolved by the priority chain (request → project default → system).
            from app.services.workflow_resolver import WorkflowResolver

            resolved_workflow_id = WorkflowResolver(self.session).resolve(
                data.type,
                request_workflow_id=data.workflow_id,
                project_id=project_id,
            )
            self._live_workflow_guard(resolved_workflow_id, provider)

        # ADR-002: resolve the authoritative SHOT_IMAGE prompt version; the
        # deprecated shot columns are the fallback (legacy rows / explicit API prompt).
        prompt_version_id: str | None = None
        from app.services.prompt_service import PromptService

        prompt_service = PromptService(self.session)
        prompt_row = prompt_service.get_prompt("SHOT", shot_id, "SHOT_IMAGE")
        active_version = prompt_service.get_active_version(prompt_row) if prompt_row else None
        if active_version is not None:
            prompt_version_id = active_version.id
        resolved_prompt = (
            data.prompt
            or (active_version.positive_prompt if active_version else None)
            or shot.image_prompt
        )
        resolved_negative = (
            data.negative_prompt
            or (active_version.negative_prompt if active_version else None)
            or shot.negative_prompt
        )
        if not resolved_prompt and data.type == "video":
            # 视频的提示词兜底：镜头动作描述（种子/手排镜头常只有 action）。
            resolved_prompt = getattr(shot, "action", None)
        if not resolved_prompt:
            raise ValidationError(
                "Shot has no image_prompt. Set a prompt before generating.",
                {"shot_id": shot_id},
            )

        generation = Generation(
            project_id=project_id,
            shot_id=shot_id,
            type=data.type,
            provider=provider,
            workflow_id=resolved_workflow_id,
            prompt_version_id=prompt_version_id,
            run_id=run_id,  # P2-E3-T03: agent provenance (approved generate_image proposal)
            status="queued",
            parameters=json.dumps(
                {
                    "prompt": resolved_prompt,
                    "negative_prompt": resolved_negative,
                    "seed": data.seed,
                    "width": data.width,
                    "height": data.height,
                    "seconds": getattr(data, "seconds", None),
                },
                ensure_ascii=False,
            ),
            # Retry budget: explicit request override, else the configured default
            # (settings.generation_max_attempts, default 3). Wiring the setting here
            # is what makes transient-failure retry and crash re-queue actually live.
            max_attempts=data.max_attempts or settings.generation_max_attempts,
            progress=0,
            stage="queued",
        )
        self.session.add(generation)
        self.session.flush()  # assign generation.id for input rows
        # P3-T012: record what this generation consumed (sparse rows).
        # PROMPT_VERSION -> the active shot image prompt when resolved (ADR-002).
        if prompt_version_id:
            self.session.add(
                GenerationInput(
                    generation_id=generation.id,
                    input_type="prompt",
                    reference_type="PROMPT_VERSION",
                    reference_id=prompt_version_id,
                    role="PROMPT_VERSION",
                    order_index=1000.0,
                )
            )
        # SHOT -> the shot the generation targets (identity/context reference).
        self.session.add(
            GenerationInput(
                generation_id=generation.id,
                input_type="reference",
                reference_type="SHOT",
                reference_id=shot_id,
                role="SHOT",
                order_index=2000.0,
            )
        )
        # P3-T012 (P2-T007 link) + M1: CHARACTER_REFERENCE rows are the worker's only
        # reference source (worker reads this table back — no duplicate storage).
        # Explicit reference_asset_ids REPLACE the auto ShotCharacter→MASTER resolution
        # (consistency preresearch §5.1); None keeps the existing auto behavior.
        explicit_refs = data.reference_asset_ids is not None
        refs = (
            self._explicit_references(project_id, data.reference_asset_ids)
            if explicit_refs
            else self._character_references(shot_id)
        )
        for idx, ref in enumerate(refs):
            metadata: dict = {"asset_id": ref["asset_id"]}
            if ref.get("character_id"):
                metadata["character_id"] = ref["character_id"]
            if explicit_refs:
                metadata["source"] = "explicit"
            self.session.add(
                GenerationInput(
                    generation_id=generation.id,
                    input_type="reference",
                    reference_type="CHARACTER_REFERENCE",
                    reference_id=ref["version_id"] or ref["asset_id"],
                    role="character_reference",
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                    order_index=3000.0 + float(idx),  # preserve resolution order for the worker
                )
            )
        # 场景一致性（自主迭代 03）：显式参考图 REPLACE 全部自动解析（角色+地点）；
        # 仅自动模式下追加地点 MASTER 参考图。order_index 排在角色之后——
        # worker 按 order_index 顺序取前 MAX_REFERENCE_IMAGES 张，角色保面容优先，
        # 地点兜底（多角色场景下超限时地点最后被裁剪，符合 3 槽位设计）。
        if not explicit_refs:
            for loc_ref in self._location_references(shot_id):
                self.session.add(
                    GenerationInput(
                        generation_id=generation.id,
                        input_type="reference",
                        reference_type="LOCATION_REFERENCE",
                        reference_id=loc_ref["version_id"] or loc_ref["asset_id"],
                        role="location_reference",
                        metadata_json=json.dumps(
                            {
                                "asset_id": loc_ref["asset_id"],
                                "location_id": loc_ref["location_id"],
                            },
                            ensure_ascii=False,
                        ),
                        order_index=4000.0,
                    )
                )
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_CREATED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=project_id,
                payload={"shot_id": shot_id, "status": generation.status},
            )
        )
        from app.generations.worker import enqueue_generation

        enqueue_generation(generation.id)
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_QUEUED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=project_id,
                payload={"shot_id": shot_id},
            )
        )
        logger.info("generation %s created for shot %s (provider=%s)", generation.id, shot_id, generation.provider)
        return generation

    def get_generation(self, generation_id: str) -> Generation:
        generation = self.session.get(Generation, generation_id)
        if generation is None or generation.deleted_at:
            raise NotFoundError("Generation does not exist.", {"generation_id": generation_id})
        return generation

    def preview_references(self, shot_id: str) -> list[dict]:
        """M1 + 自主迭代 03：预览该镜头生成「自动模式」将注入的角色 + 场景地点参考图。

        与 create_generation 的自动解析完全同源（_character_references +
        _location_references），只是额外带上 character_name / location_name 供 UI
        展示。返回全部解析结果（不截断到引擎 3 图上限）——超过上限时由前端提示
        「仅前 N 张会被注入」，用户可切手动模式精选。
        """
        shot = self.shots.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        char_refs = self._character_references(shot_id)
        loc_refs = self._location_references(shot_id)
        if not char_refs and not loc_refs:
            return []
        from app.db.models import Character, Location

        names = {
            c.id: c.name
            for c in self.session.scalars(
                select(Character).where(Character.id.in_([r["character_id"] for r in char_refs if r.get("character_id")]))
            )
        }
        character_items = [{**r, "character_name": names.get(r.get("character_id"))} for r in char_refs]
        location_items: list[dict] = []
        for r in loc_refs:
            loc = self.session.get(Location, r["location_id"])
            location_items.append({**r, "location_name": loc.name if loc else None})
        return [*character_items, *location_items]

    def generation_references(self, generation_id: str) -> list[dict]:
        """M1 + 自主迭代 03：读回单条生成的 CHARACTER/LOCATION_REFERENCE 溯源行。

        供 GET /generations/{id} 明细展示（生成后 provenance 可视化）；
        metadata_json.asset_id / character_id / location_id / source 与 create
        写入侧对称。
        """
        generation = self.get_generation(generation_id)
        rows = list(
            self.session.scalars(
                select(GenerationInput)
                .where(
                    GenerationInput.generation_id == generation.id,
                    GenerationInput.role.in_(("character_reference", "location_reference")),
                )
                .order_by(GenerationInput.order_index)
            )
        )
        refs: list[dict] = []
        character_ids: list[str] = []
        location_ids: list[str] = []
        for row in rows:
            meta: dict = {}
            if row.metadata_json:
                try:
                    meta = json.loads(row.metadata_json)
                except ValueError:
                    meta = {}
            asset_id = meta.get("asset_id") or row.reference_id
            if not asset_id:
                continue
            character_id = meta.get("character_id")
            location_id = meta.get("location_id")
            if character_id:
                character_ids.append(character_id)
            if location_id:
                location_ids.append(location_id)
            refs.append(
                {
                    "character_id": character_id,
                    "character_name": None,  # 批量回填，避免 N+1
                    "location_id": location_id,
                    "location_name": None,  # 批量回填，避免 N+1
                    # 写入侧：auto 行 reference_id=version_id；explicit 行
                    # reference_id=asset_id（无版本语义）——按二者是否相等区分。
                    "version_id": row.reference_id if row.reference_id != asset_id else None,
                    "asset_id": asset_id,
                    "source": meta.get("source") or "auto",
                }
            )
        if character_ids:
            from app.db.models import Character

            names = {
                c.id: c.name
                for c in self.session.scalars(select(Character).where(Character.id.in_(character_ids)))
            }
            for ref in refs:
                if ref["character_id"]:
                    ref["character_name"] = names.get(ref["character_id"])
        if location_ids:
            from app.db.models import Location

            names = {
                loc.id: loc.name
                for loc in self.session.scalars(select(Location).where(Location.id.in_(location_ids)))
            }
            for ref in refs:
                if ref["location_id"]:
                    ref["location_name"] = names.get(ref["location_id"])
        return refs

    def list_generations(self, shot_id: str | None = None, status: str | None = None) -> list[Generation]:
        from sqlalchemy import select

        stmt = select(Generation).where(Generation.deleted_at.is_(None))
        if shot_id:
            stmt = stmt.where(Generation.shot_id == shot_id)
        if status:
            stmt = stmt.where(Generation.status == status)
        stmt = stmt.order_by(Generation.created_at.desc())
        return list(self.session.scalars(stmt))

    def list_recent(self, limit: int = 20) -> list[Generation]:
        """Recent generations across all shots (bottom dock history; P1-E4-T01:
        query lives in the Service, not the Router)."""
        from sqlalchemy import select

        stmt = (
            select(Generation)
            .where(Generation.deleted_at.is_(None))
            .order_by(Generation.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def retry_generation(self, generation_id: str) -> Generation:
        original = self.get_generation(generation_id)
        if original.status in ("queued", "running", "retrying"):
            raise ConflictError(
                "Cannot retry a generation that is still running.",
                {"generation_id": generation_id, "status": original.status},
            )
        if original.shot_id is None:
            raise ConflictError("Generation has no shot to retry.", {"generation_id": generation_id})
        params = json.loads(original.parameters or "{}")
        retry = self.create_generation(
            original.shot_id,
            GenerationCreate(
                type=original.type,
                provider=original.provider,
                workflow_id=original.workflow_id,
                prompt=params.get("prompt"),
                negative_prompt=params.get("negative_prompt"),
                seed=params.get("seed"),
                width=params.get("width"),
                height=params.get("height"),
            ),
        )
        retry.retry_of = generation_id
        self.session.commit()
        logger.info("generation %s retried as %s", generation_id, retry.id)
        return retry

    def cancel_generation(self, generation_id: str) -> Generation:
        """Cancel via the state machine (P1-E2-T02): illegal transitions are a
        Domain Error (409), never a silent write.

        P5-T015: a queued/retrying row is cancelled immediately (durable). A RUNNING
        row is moved to the durable 'cancelling' state so the cancel survives a restart;
        the worker finalizes it to 'cancelled' once it notices. The final
        generation.cancelled event is emitted by the worker on finalize.
        """
        from app.generations.state import validate_transition

        generation = self.get_generation(generation_id)
        if generation.status in ("queued", "retrying"):
            validate_transition(generation.status, "cancelled")
            generation.status = "cancelled"
            generation.completed_at = generation.completed_at or self._now()
            self.session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_CANCELLED,
                    entity_type="generation",
                    entity_id=generation.id,
                    project_id=generation.project_id,
                    payload={"shot_id": generation.shot_id},
                )
            )
        elif generation.status == "running":
            # Durable cancel marker for an actively running job.
            validate_transition(generation.status, "cancelling")
            generation.status = "cancelling"
            self.session.commit()
            # The worker finalizes running→cancelled and emits generation.cancelled.
        else:
            # completed / failed / cancelled / interrupted / cancelling → 409.
            validate_transition(generation.status, "cancelled")  # raises ConflictError
        return generation

    @staticmethod
    def _now() -> str:
        from datetime import datetime

        return datetime.now(UTC).isoformat()

    def _character_references(self, shot_id: str) -> list[dict]:
        """P3-T012 (P2-T007 link): shot characters' MASTER CharacterVersion assets.

        For each character linked to the shot with a non-null master_version_id, emit
        {character_id, version_id, asset_id} so provenance records what visual standard a
        generation should reference. Characters without a master version are skipped.
        """
        from sqlalchemy import select

        from app.db.models import Character, CharacterVersion, ShotCharacter

        links = self.session.scalars(
            select(ShotCharacter).where(ShotCharacter.shot_id == shot_id)
        ).all()
        if not links:
            return []
        character_ids = [link.character_id for link in links]
        characters = self.session.scalars(
            select(Character).where(
                Character.id.in_(character_ids),
                Character.deleted_at.is_(None),
                Character.master_version_id.isnot(None),
            )
        ).all()
        if not characters:
            return []
        version_ids = [c.master_version_id for c in characters if c.master_version_id]
        versions_by_id = {
            v.id: v
            for v in self.session.scalars(
                select(CharacterVersion).where(
                    CharacterVersion.id.in_(version_ids),
                    CharacterVersion.deleted_at.is_(None),
                    CharacterVersion.status == "active",
                )
            )
        }
        refs: list[dict] = []
        for c in characters:
            version = versions_by_id.get(c.master_version_id)
            if version is not None:
                refs.append(
                    {
                        "character_id": c.id,
                        "version_id": version.id,
                        "asset_id": version.asset_id,
                    }
                )
        return refs

    def _location_references(self, shot_id: str) -> list[dict]:
        """自主迭代 03：shot 所在场景绑定的 Location MASTER 参考图。

        解析链：shot → scene.location_id → Location.master_version_id →
        active LocationVersion asset。场景未绑定地点 / 地点无 MASTER 版本 /
        版本非 active → 返回空（不注入）。与 _character_references 同构，
        metadata 带 location_id 供溯源与 UI 展示。
        """
        from app.db.models import Location, LocationVersion, Scene

        shot = self.shots.get(shot_id)
        if shot is None:
            return []
        scene = self.session.get(Scene, shot.scene_id)
        if scene is None or not scene.location_id:
            return []
        location = self.session.get(Location, scene.location_id)
        if location is None or location.deleted_at or not location.master_version_id:
            return []
        version = self.session.get(LocationVersion, location.master_version_id)
        if version is None or version.deleted_at or version.status != "active":
            return []
        return [{"location_id": location.id, "version_id": version.id, "asset_id": version.asset_id}]

    def _explicit_references(self, project_id: str, asset_ids: list[str]) -> list[dict]:
        """M1: validate caller-provided reference assets (consistency preresearch §5.1).

        Every asset must exist (404), belong to the same project (422) and be an
        image ("reference" kept for the legacy dead enum). Order follows the request;
        an empty list means "explicitly no references" (auto resolution skipped).
        """
        from app.db.models import Asset

        refs: list[dict] = []
        for asset_id in asset_ids:
            asset = self.session.get(Asset, asset_id)
            if asset is None or asset.deleted_at:
                raise NotFoundError("Asset does not exist.", {"asset_id": asset_id})
            if asset.project_id != project_id:
                raise ValidationError(
                    "Asset belongs to another project.",
                    {"asset_id": asset_id, "project_id": project_id, "asset_project_id": asset.project_id},
                )
            if asset.type not in ("image", "reference"):
                raise ValidationError(
                    "Reference asset must be an image.",
                    {"asset_id": asset_id, "type": asset.type},
                )
            refs.append({"character_id": None, "version_id": None, "asset_id": asset.id})
        return refs

    def _live_workflow_guard(self, workflow_id: str, provider: str) -> None:
        """P2-E4-T02 检查通道 fail-fast：comfyui provider 且 live 诊断发现
        确定性问题（缺节点/缺模型/断链）→ 422，任务绝不带着必败 workflow 排队。

        宽容语义：ComfyUI 不可达 / 诊断自身异常 → 放行（202 照旧，worker 运行
        时诚实失败）——检查通道降级绝不阻断生产通道。同步原生通道（路由在线程池，
        Agent 工具在运行中的事件循环内，均不可 asyncio.run）。
        """
        if provider != "comfyui":
            return
        try:
            from app.services.workflow_diagnostics_service import get_workflow_diagnostics_service

            diagnostics = get_workflow_diagnostics_service().validate_workflow_sync(workflow_id)
        except Exception as exc:  # noqa: BLE001 — 诊断崩溃永不阻断排队
            logger.warning("live workflow guard skipped: %s", exc)
            return
        if diagnostics.status == "invalid":
            raise ValidationError(
                "Workflow cannot run on the connected ComfyUI.",
                {
                    "workflow_id": diagnostics.workflow_id,
                    "missing_nodes": diagnostics.missing_nodes,
                    "missing_models": diagnostics.missing_models,
                    "broken_links": diagnostics.broken_links,
                },
            )

    def _project_id_of(self, shot: Shot) -> str | None:
        from app.db.models import Episode, Scene

        scene = self.session.get(Scene, shot.scene_id)
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
