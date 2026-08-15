"""Provenance API (P3-T012/T013; ADR-001 §3; Alpha backend design §110).

- GET /assets/{asset_id}/provenance   → asset + producing generation + inputs + retry chain
- GET /generations/{generation_id}/inputs
- GET /generations/{generation_id}/outputs

All business reads live in ProvenanceService (Router → Service red line).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.provenance import (
    AssetProvenanceRead,
    GenerationInputRead,
    GenerationInputsRead,
    GenerationOutputRead,
    GenerationOutputsRead,
    GenerationProvenanceBlock,
)
from app.services import ProvenanceService

router = APIRouter(tags=["provenance"])


@router.get("/assets/{asset_id}/provenance", response_model=AssetProvenanceRead)
def asset_provenance(asset_id: str, db: Session = Depends(get_db)) -> AssetProvenanceRead:
    data = ProvenanceService(db).build_asset_provenance(asset_id)
    return AssetProvenanceRead(
        asset=data["asset"],
        generation=(
            GenerationProvenanceBlock(**data["generation"]) if data["generation"] else None
        ),
        inputs=[GenerationInputRead(**i) for i in data["inputs"]],
        retry_of=data["retry_of"],
        parent_asset_id=data["parent_asset_id"],
        ancestors=data["ancestors"],
    )


@router.get("/generations/{generation_id}/inputs", response_model=GenerationInputsRead)
def generation_inputs(generation_id: str, db: Session = Depends(get_db)) -> GenerationInputsRead:
    rows = ProvenanceService(db).get_generation_inputs(generation_id)
    return GenerationInputsRead(
        generation_id=generation_id,
        inputs=[GenerationInputRead(**i) for i in rows],
    )


@router.get("/generations/{generation_id}/outputs", response_model=GenerationOutputsRead)
def generation_outputs(generation_id: str, db: Session = Depends(get_db)) -> GenerationOutputsRead:
    rows = ProvenanceService(db).get_generation_outputs(generation_id)
    return GenerationOutputsRead(
        generation_id=generation_id,
        outputs=[GenerationOutputRead(**o) for o in rows],
    )
