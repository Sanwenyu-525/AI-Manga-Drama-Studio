"""LLM runtime connection management（单连接 legacy + 多连接 Profile Registry）.

Settings UI 的连接面：
GET  /api/v1/llm/config      → 激活连接生效配置（api_key masked）
PUT  /api/v1/llm/config      → 更新激活连接，重置 gateway 缓存
POST /api/v1/llm/test        → 连通性探测（可测未保存参数 / 指定 profile；never raises）
GET  /api/v1/llm/models      → 端点模型 id 列表（可指定 profile）
POST /api/v1/llm/detect-local → 本机 OpenAI 兼容服务探测（never raises）

多连接 Profile（P-LLM-Profiles）：
GET    /api/v1/llm/profiles                  → 列表 + 激活 id + 任务绑定
POST   /api/v1/llm/profiles                  → 新建连接
PATCH  /api/v1/llm/profiles/{id}             → 局部更新
DELETE /api/v1/llm/profiles/{id}             → 删除（激活连接禁删）
POST   /api/v1/llm/profiles/{id}/activate    → 切换激活连接
PUT    /api/v1/llm/task-bindings             → 任务 → 连接绑定
PUT    /api/v1/llm/task-fallbacks            → 任务 → 有序降级链（显式配置，事件宣告）
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.llm_settings_service import (
    activate_llm_profile,
    create_llm_profile,
    delete_llm_profile,
    detect_local_llm_servers,
    get_config_read,
    list_llm_models,
    list_llm_profiles,
    set_task_bindings,
    set_task_fallbacks,
    test_llm_connection,
    update_llm_config,
    update_llm_profile,
)

router = APIRouter(tags=["llm"])


class LLMConfigUpdate(BaseModel):
    mode: Literal["fake", "openai"] | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class LLMProfileCreate(BaseModel):
    name: str | None = None
    mode: Literal["fake", "openai"] = "fake"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    capabilities: dict[str, bool] | None = Field(
        default=None, description="能力覆写（tools/vision/reasoning），声明后优先于启发式"
    )


class LLMProfileUpdate(BaseModel):
    name: str | None = None
    mode: Literal["fake", "openai"] | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    capabilities: dict[str, bool] | None = None


class LLMTestRequest(BaseModel):
    """Optional unsaved overrides so the UI can test-before-save.

    api_key is only sent when the user typed a new one; otherwise the backend
    tests with the stored key. profile_id 指定测试某条已存连接（未存参数仍可叠加）。"""

    profile_id: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class LLMTaskBindingsUpdate(BaseModel):
    bindings: dict[str, str | None]


class LLMTaskFallbacksUpdate(BaseModel):
    """task → 有序降级连接列表（P-LLM-Fallback）。空列表 = 清除 = 回到 fail-fast。"""

    fallbacks: dict[str, list[str]]


@router.get("/llm/config")
def read_llm_config() -> dict[str, Any]:
    return get_config_read()


@router.put("/llm/config")
def write_llm_config(update: LLMConfigUpdate) -> dict[str, Any]:
    # 只提交显式给出的字段；省略字段保持原值，api_key 未改动时不回传。
    provided = {key: getattr(update, key) for key in update.model_fields_set}
    return update_llm_config(provided)


# ------------------------------------------------------------- profiles --------


@router.get("/llm/profiles")
def read_llm_profiles() -> dict[str, Any]:
    return list_llm_profiles()


@router.post("/llm/profiles")
def add_llm_profile(body: LLMProfileCreate) -> dict[str, Any]:
    provided = {key: getattr(body, key) for key in body.model_fields_set}
    return create_llm_profile(provided)


@router.patch("/llm/profiles/{profile_id}")
def patch_llm_profile(profile_id: str, body: LLMProfileUpdate) -> dict[str, Any]:
    provided = {key: getattr(body, key) for key in body.model_fields_set}
    return update_llm_profile(profile_id, provided)


@router.delete("/llm/profiles/{profile_id}")
def remove_llm_profile(profile_id: str) -> dict[str, Any]:
    return delete_llm_profile(profile_id)


@router.post("/llm/profiles/{profile_id}/activate")
def activate_profile(profile_id: str) -> dict[str, Any]:
    return activate_llm_profile(profile_id)


@router.put("/llm/task-bindings")
def put_task_bindings(body: LLMTaskBindingsUpdate) -> dict[str, Any]:
    return set_task_bindings(body.bindings)


@router.put("/llm/task-fallbacks")
def put_task_fallbacks(body: LLMTaskFallbacksUpdate) -> dict[str, Any]:
    """显式降级链（不静默掩盖模型故障）：链上只有用户配置过的连接；
    降级发生时后端发 llm.fallback.used 事件 + WARNING 日志 + 响应归因。"""
    return set_task_fallbacks(body.fallbacks)


# ------------------------------------------------------------- test / models ----


@router.post("/llm/test")
async def test_llm(req: LLMTestRequest | None = None) -> dict[str, Any]:
    """Connectivity probe mirroring /providers/comfyui/test: 200 + connected flag."""
    provided = req.model_dump(exclude_none=True) if req is not None else None
    return await test_llm_connection(provided)


@router.get("/llm/models")
async def read_llm_models(profile_id: str | None = None) -> dict[str, Any]:
    return {"models": await list_llm_models(profile_id)}


@router.post("/llm/detect-local")
async def detect_local_llm() -> dict[str, Any]:
    """Probe common local OpenAI-compatible servers; 200 + {servers: [...]} always."""
    return await detect_local_llm_servers()
