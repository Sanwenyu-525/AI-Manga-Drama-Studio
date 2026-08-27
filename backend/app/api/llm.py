"""LLM runtime connection settings (mode / base_url / api_key / model).

Lets the settings UI change the LLM connection without editing env or restarting:
GET  /api/v1/llm/config  → effective config (api_key masked)
PUT  /api/v1/llm/config  → partial update, resets the cached gateway
POST /api/v1/llm/test    → connectivity probe (accepts unsaved overrides; never raises)
GET  /api/v1/llm/models  → model ids from the saved OpenAI-compatible endpoint
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.llm_settings_service import (
    get_config_read,
    list_llm_models,
    test_llm_connection,
    update_llm_config,
)

router = APIRouter(tags=["llm"])


class LLMConfigUpdate(BaseModel):
    mode: Literal["fake", "openai"] | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class LLMTestRequest(BaseModel):
    """Optional unsaved overrides so the UI can test-before-save.

    api_key is only sent when the user typed a new one; otherwise the backend
    tests with the stored key."""

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


@router.get("/llm/config")
def read_llm_config() -> dict[str, Any]:
    return get_config_read()


@router.put("/llm/config")
def write_llm_config(update: LLMConfigUpdate) -> dict[str, Any]:
    # 只提交显式给出的字段；省略字段保持原值，api_key 未改动时不回传。
    provided = {key: getattr(update, key) for key in update.model_fields_set}
    return update_llm_config(provided)


@router.post("/llm/test")
async def test_llm(req: LLMTestRequest | None = None) -> dict[str, Any]:
    """Connectivity probe mirroring /providers/comfyui/test: 200 + connected flag."""
    provided = req.model_dump(exclude_none=True) if req is not None else None
    return await test_llm_connection(provided)


@router.get("/llm/models")
async def read_llm_models() -> dict[str, Any]:
    return {"models": await list_llm_models()}
