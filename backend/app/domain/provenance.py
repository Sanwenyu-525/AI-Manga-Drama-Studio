"""Provenance DTOs (P3-T012/T013; ADR-001 §3; Alpha backend design §110).

GET /assets/{asset_id}/provenance:
  { asset, generation, inputs, retry_of, parent_asset_id, ancestors }

generation.parameters is the raw generation JSON string (parsed at the call site);
generation exposes id/type/provider/model/workflow_id/prompt_version_id/status/
created_at/completed_at.
"""

from pydantic import BaseModel


class GenerationInputRead(BaseModel):
    id: str
    generation_id: str
    input_type: str
    reference_type: str | None
    reference_id: str | None
    role: str | None
    order_index: float
    metadata_json: str | None


class GenerationOutputRead(BaseModel):
    generation_id: str
    asset_id: str
    role: str | None
    order_index: float
    type: str | None = None       # asset.type
    status: str | None = None     # asset.status
    version_number: int | None = None
    file_path: str | None = None


class GenerationProvenanceBlock(BaseModel):
    id: str
    type: str
    provider: str
    model: str | None
    workflow_id: str | None
    prompt_version_id: str | None
    status: str | None
    created_at: str | None
    completed_at: str | None
    parameters: str | None


class AssetProvenanceRead(BaseModel):
    asset: dict
    generation: GenerationProvenanceBlock | None
    inputs: list[GenerationInputRead]
    retry_of: str | None
    parent_asset_id: str | None
    ancestors: list[str]  # retry chain, oldest first, excluding this generation


class GenerationInputsRead(BaseModel):
    generation_id: str
    inputs: list[GenerationInputRead]


class GenerationOutputsRead(BaseModel):
    generation_id: str
    outputs: list[GenerationOutputRead]
