"""Image generation runtime settings (provider / agnes base_url / api_key).

Mirrors /llm/config: lets the settings UI switch the image provider and store the
Agnes key without editing env or restarting.
GET  /api/v1/image/config        → effective config (api_key masked)
PUT  /api/v1/image/config        → partial update, resets cached image providers
GET  /api/v1/image/video-models  → video model catalog + best-effort availability
POST /api/v1/image/test          → connectivity probe (never raises, no quota usage)
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.image_settings_service import (
    get_config_read,
    list_video_models,
    test_image_connection,
    update_image_config,
)

router = APIRouter(tags=["image-settings"])


class ImageConfigUpdate(BaseModel):
    provider: Literal["mock", "comfyui", "agnes"] | None = None
    agnes_base_url: str | None = None
    api_key: str | None = None
    video_provider: Literal["mock", "agnes"] | None = None
    video_model: str | None = None
    # ComfyUI 本地链路（空字符串 = 清除覆盖回落 env/默认值；省略 = 不动）
    comfyui_url: str | None = None
    checkpoint: str | None = None
    comfyui_models_root: str | None = None


class ImageTestRequest(BaseModel):
    provider: Literal["mock", "comfyui", "agnes"] | None = None
    agnes_base_url: str | None = None
    api_key: str | None = None


@router.get("/image/config")
def read_image_config() -> dict[str, Any]:
    return get_config_read()


@router.get("/image/video-models")
def read_video_models() -> dict[str, Any]:
    """视频模型目录（后端单一事实源）+ best-effort 实测可用性。"""
    return list_video_models()


@router.put("/image/config")
def write_image_config(update: ImageConfigUpdate) -> dict[str, Any]:
    return update_image_config(update.model_dump(exclude_none=True))


@router.post("/image/test")
def test_image(req: ImageTestRequest | None = None) -> dict[str, Any]:
    return test_image_connection(req.model_dump(exclude_none=True) if req is not None else None)
