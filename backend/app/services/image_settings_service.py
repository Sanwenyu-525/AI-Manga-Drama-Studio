"""Image generation runtime settings (provider / base_url / api_key).

Mirrors llm_settings_service: the settings UI can switch the image provider and
store the Agnes key without editing env or restarting.
GET  /api/v1/image/config  → effective config (api_key masked)
PUT  /api/v1/image/config  → partial update, resets cached image providers
POST /api/v1/image/test    → connectivity probe (never raises, no quota usage)

Storage: data_dir/image.json (overrides only; env stays the fallback layer).
Key policy matches LLM: stored server-side, never echoed back to the client.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ValidationError
# 默认 checkpoint 与 workflow_schema 的 $CHECKPOINT 默认值同源（单一事实源在 schema）。
from app.core.logging import get_logger
from app.providers.comfyui.workflow_schema import DEFAULT_CHECKPOINT

logger = get_logger("services.image_settings")

# 视频模型目录：「视频服务」下拉的唯一事实源（前端不再硬编码）。
# verified=True → 已按 agnes.py 头部契约实测出片；False → 候选（v2.0 仅适配了返回
# 结构，未实测出片），UI 标「未验证」。available 由 GET {base}/models 实测填充。
VIDEO_MODELS: list[dict[str, Any]] = [
    {"id": "agnes-video-2.5-flash", "label": "快 · 当前免费", "verified": True},
    {"id": "agnes-video-v2.0", "label": "当前免费 · 返回结构已适配", "verified": False},
    {"id": "agnes-video-2.5", "label": None, "verified": False},
]

_PROVIDER_CHOICES = ("mock", "comfyui", "agnes")
_VIDEO_PROVIDER_CHOICES = ("mock", "agnes")
_PROBE_TIMEOUT = 10.0
IMAGE_CONFIG_FILE = "image.json"


def _path() -> Any:
    return settings.data_dir / IMAGE_CONFIG_FILE


def _read_overrides() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(overrides: dict[str, Any]) -> None:
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")


def get_image_config() -> dict[str, Any]:
    """Effective runtime image config: env defaults overridden by the JSON layer."""
    over = _read_overrides()
    provider = over.get("provider") if over.get("provider") in _PROVIDER_CHOICES else settings.image_provider
    return {
        "provider": provider,
        "agnes_base_url": (over.get("agnes_base_url") or None) or settings.agnes_base_url,
        "api_key": (over.get("api_key") or None) or settings.agnes_api_key,
        # ComfyUI 本地链路：地址 / 生成用 checkpoint / ComfyUI 模型根目录（导入目标）。
        "comfyui_url": (over.get("comfyui_url") or None) or settings.comfyui_url,
        "checkpoint": (over.get("checkpoint") or None) or DEFAULT_CHECKPOINT,
        "comfyui_models_root": (over.get("comfyui_models_root") or None) or None,
    }


def get_config_read() -> dict[str, Any]:
    """Safe read shape for the API — never echoes the full api_key."""
    cfg = get_image_config()
    video = get_video_config()
    key = cfg["api_key"] or ""
    return {
        "provider": cfg["provider"],
        "agnes_base_url": cfg["agnes_base_url"],
        "api_key_set": bool(key),
        "api_key_hint": f"****{key[-4:]}" if len(key) >= 4 else None,
        "video_provider": video["provider"],
        "video_model": video["model"],
        "comfyui_url": cfg["comfyui_url"],
        "checkpoint": cfg["checkpoint"],
        "comfyui_models_root": cfg["comfyui_models_root"],
    }


def get_video_config() -> dict[str, Any]:
    """视频生成运行时配置：Agnes key/base_url 与图像服务共用同一账号。"""
    over = _read_overrides()
    provider = over.get("video_provider") if over.get("video_provider") in _VIDEO_PROVIDER_CHOICES else settings.video_provider
    model = (over.get("video_model") or None) or settings.video_model
    base = (over.get("agnes_base_url") or None) or settings.agnes_base_url
    key = (over.get("api_key") or None) or settings.agnes_api_key
    return {"provider": provider, "model": model, "agnes_base_url": base, "api_key": key}


def list_video_models() -> dict[str, Any]:
    """视频模型目录 + best-effort 实测可用性（探测 GET {base}/models，不消耗额度）。

    未配置 key / 探测失败永不抛错：available 留空并在 probe_error 说明，
    UI 只显示目录与「未验证」标记。
    """
    result: dict[str, Any] = {
        "models": [dict(m, available=None) for m in VIDEO_MODELS],
        "probed": False,
        "probe_error": None,
    }
    cfg = get_video_config()
    key = cfg.get("api_key") or ""
    base = (cfg.get("agnes_base_url") or "").rstrip("/")
    if not key or not base:
        return result
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT, trust_env=False) as client:
            resp = client.get(base + "/models", headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        result["probe_error"] = f"可用性探测失败：{exc}"
        return result
    if resp.status_code != 200:
        result["probe_error"] = f"可用性探测失败：HTTP {resp.status_code}"
        return result
    try:
        ids = {str(m.get("id")) for m in resp.json().get("data", []) if isinstance(m, dict) and m.get("id")}
    except ValueError:
        result["probe_error"] = "可用性探测失败：响应不是有效 JSON"
        return result
    for m in result["models"]:
        m["available"] = m["id"] in ids
    result["probed"] = True
    return result


def update_image_config(update: dict[str, Any]) -> dict[str, Any]:
    """Partial update: omitted keys keep current settings; ComfyUI/video 字段显式传
    "" 时清除覆盖回落 env/默认值（provider/agnes_base_url/api_key 沿用 merged 语义）。"""
    cur = get_image_config()
    overrides = _read_overrides()
    # video_model 只接受目录内模型（目录即前端下拉事实源；显式空值走清除分支不校验）
    if update.get("video_model") not in (None, "") and update["video_model"] not in {m["id"] for m in VIDEO_MODELS}:
        raise ValidationError(
            f"未知视频模型：{update['video_model']}",
            {"allowed": [m["id"] for m in VIDEO_MODELS]},
        )
    merged = {
        **{k: v for k, v in cur.items()},
        **{k: v for k, v in update.items() if v not in (None, "")},
    }
    for key in ("provider", "agnes_base_url", "api_key"):
        overrides[key] = merged[key]  # merged 值：update 未提供时保持当前值不变
    # 以下字段只在请求显式给出时才生效：省略 = 不动；显式空值 = 清除覆盖回落 env/默认。
    for key in ("video_provider", "video_model", "comfyui_url", "checkpoint", "comfyui_models_root"):
        if key not in update:
            continue
        value = update.get(key)
        if value in (None, ""):
            overrides.pop(key, None)
        else:
            overrides[key] = value
    _write(overrides)

    # 让下次 get_image_provider() 用新配置重建（旧实例的 key/base_url 作废）；
    # reset_image_providers 同时清 ComfyUI Provider 单例（URL/checkpoint 变更生效）。
    from app.providers.registry import reset_image_providers

    reset_image_providers()
    return get_config_read()


def test_image_connection(provided: dict[str, Any] | None = None) -> dict[str, Any]:
    """Probe the (possibly unsaved) connection. Never raises, no generation quota:
    agnes → GET {base}/models with the key; mock → always connected; comfyui →
    pointer to the existing /providers/comfyui/test."""
    cfg = dict(get_image_config())
    for k, v in (provided or {}).items():
        if v not in (None, ""):
            cfg[k] = v

    provider = cfg.get("provider")
    if provider == "mock":
        return {"connected": True, "provider": "mock", "detail": "mock 无需连接（确定性占位图）"}
    if provider == "comfyui":
        return {"connected": None, "provider": "comfyui", "detail": "请使用「生成服务」里 ComfyUI 的测试连接"}

    key = cfg.get("api_key") or ""
    if not key:
        return {"connected": False, "provider": "agnes", "error": "未配置 API Key（图像服务）"}
    url = (cfg.get("agnes_base_url") or "").rstrip("/") + "/models"
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT, trust_env=False) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        return {"connected": False, "provider": "agnes", "error": f"连接失败：{exc}"}
    latency_ms = int((time.perf_counter() - started) * 1000)
    if resp.status_code in (401, 403):
        return {"connected": False, "provider": "agnes", "latency_ms": latency_ms, "error": f"鉴权失败（HTTP {resp.status_code}），请检查 API Key。"}
    if resp.status_code != 200:
        return {"connected": False, "provider": "agnes", "latency_ms": latency_ms, "error": f"HTTP {resp.status_code}"}
    try:
        ids = [str(m.get("id")) for m in resp.json().get("data", []) if isinstance(m, dict) and m.get("id")]
    except ValueError:
        ids = []
    result: dict[str, Any] = {"connected": True, "provider": "agnes", "latency_ms": latency_ms}
    if "agnes-image-2.1-flash" in ids:
        result["image_model_available"] = True
    return result


__all__ = [
    "VIDEO_MODELS",
    "get_config_read",
    "get_image_config",
    "list_video_models",
    "test_image_connection",
    "update_image_config",
]
