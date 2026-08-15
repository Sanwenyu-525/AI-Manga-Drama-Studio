"""ProvenanceService (P3-T012/T013; ADR-001 §3).

Answers provenance queries in one place:
- what a generation consumed (generation_inputs) / produced (generation_outputs)
- what produced a given asset, and the retry chain behind it.

Read-only; used by API routers and the AI Director. No LangGraph dependency (red line).
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Asset, Generation, GenerationInput, GenerationOutput


def _input_to_dict(i: GenerationInput) -> dict:
    return {
        "id": i.id,
        "generation_id": i.generation_id,
        "input_type": i.input_type,
        "reference_type": i.reference_type,
        "reference_id": i.reference_id,
        "role": i.role,
        "order_index": i.order_index,
        "metadata_json": i.metadata_json,
    }


def _asset_summary(a: Asset) -> dict:
    import json as _json

    meta = None
    if a.meta_json:
        try:
            meta = _json.loads(a.meta_json)
        except (ValueError, TypeError):
            meta = None
    return {
        "id": a.id,
        "project_id": a.project_id,
        "type": a.type,
        "name": a.name,
        "file_path": a.file_path,
        "mime_type": a.mime_type,
        "width": a.width,
        "height": a.height,
        "status": a.status,
        "source_type": a.source_type,
        "version_group_id": a.version_group_id,
        "version_number": a.version_number,
        "generation_id": a.generation_id,
        "parent_asset_id": a.parent_asset_id,
        "meta": meta,
        "created_at": a.created_at,
    }


class ProvenanceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- generation-level queries ---

    def get_generation(self, generation_id: str) -> Generation:
        g = self.session.get(Generation, generation_id)
        if g is None or g.deleted_at:
            raise NotFoundError("Generation does not exist.", {"generation_id": generation_id})
        return g

    def get_generation_inputs(self, generation_id: str) -> list[dict]:
        """Ordered consumed inputs (order_index asc) for a generation."""
        self.get_generation(generation_id)
        rows = list(
            self.session.scalars(
                select(GenerationInput)
                .where(GenerationInput.generation_id == generation_id)
                .order_by(GenerationInput.order_index.asc(), GenerationInput.id)
            )
        )
        return [_input_to_dict(r) for r in rows]

    def get_generation_outputs(self, generation_id: str) -> list[dict]:
        """Produced assets (order_index asc), enriched with asset summary fields."""
        self.get_generation(generation_id)
        rows = list(
            self.session.scalars(
                select(GenerationOutput)
                .where(GenerationOutput.generation_id == generation_id)
                .order_by(GenerationOutput.order_index.asc(), GenerationOutput.asset_id)
            )
        )
        outputs: list[dict] = []
        for row in rows:
            asset = self.session.get(Asset, row.asset_id)
            outputs.append(
                {
                    "generation_id": row.generation_id,
                    "asset_id": row.asset_id,
                    "role": row.role,
                    "order_index": row.order_index,
                    "type": asset.type if asset else None,
                    "status": asset.status if asset else None,
                    "version_number": asset.version_number if asset else None,
                    "file_path": asset.file_path if asset else None,
                }
            )
        return outputs

    # --- asset-level provenance ---

    def build_asset_provenance(self, asset_id: str) -> dict:
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at:
            raise NotFoundError("Asset does not exist.", {"asset_id": asset_id})

        # Which generation produced it? Prefer the join row, fall back to the
        # denormalized assets.generation_id (legacy assets without a join row).
        generation_id = asset.generation_id
        join_row = self.session.scalar(
            select(GenerationOutput).where(GenerationOutput.asset_id == asset_id)
        )
        if join_row is not None:
            generation_id = join_row.generation_id

        generation_block = None
        retry_of = None
        if generation_id:
            gen = self.session.get(Generation, generation_id)
            if gen is not None:
                generation_block = {
                    "id": gen.id,
                    "type": gen.type,
                    "provider": gen.provider,
                    "model": gen.model,
                    "workflow_id": gen.workflow_id,
                    "prompt_version_id": gen.prompt_version_id,
                    "status": gen.status,
                    "created_at": gen.created_at,
                    "completed_at": gen.completed_at,
                    "parameters": gen.parameters,
                }
                retry_of = gen.retry_of

        inputs = self.get_generation_inputs(generation_id) if generation_id else []

        # walk the retry chain (each generation.retry_of points at its parent)
        ancestors: list[str] = []
        seen: set[str] = set()
        cursor = retry_of
        while cursor:
            if cursor in seen:
                break
            seen.add(cursor)
            ancestors.append(cursor)
            parent = self.session.get(Generation, cursor)
            if parent is None:
                break
            cursor = parent.retry_of

        return {
            "asset": _asset_summary(asset),
            "generation": generation_block,
            "inputs": inputs,
            "retry_of": retry_of,
            "parent_asset_id": asset.parent_asset_id,
            "ancestors": list(reversed(ancestors)) if ancestors else [],
        }


def parse_parameters(raw: str | None) -> dict:
    """Best-effort parse of a generation.parameters JSON string."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}
