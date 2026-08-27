"""Runtime LLM connection config (mode / base_url / api_key / model).

Precedence: the backend env (app.core.config.Settings) supplies defaults;
an optional `{data_dir}/llm.json` override layer lets the settings API change the
connection at runtime. Updating the config resets the cached gateway so the next
Agent / ScriptService call picks up the new connection (no restart required).

This is connection plumbing only — it never stores any project content, so it is
not "Project State" (AGENTS §3 rule 11).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import ValidationError

LLM_CONFIG_FILE = "llm.json"
_MODE_CHOICES = ("fake", "openai")


def _path() -> Path:
    return settings.data_dir / LLM_CONFIG_FILE


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


def get_llm_config() -> dict[str, Any]:
    """Effective runtime LLM config: env defaults overridden by the JSON layer."""
    over = _read_overrides()
    mode = over.get("mode") if over.get("mode") in _MODE_CHOICES else settings.llm_mode
    return {
        "mode": mode,
        "base_url": (over.get("base_url") or None) or settings.llm_base_url,
        "api_key": (over.get("api_key") or None) or settings.llm_api_key,
        "model": (over.get("model") or None) or settings.llm_model,
    }


def get_config_read() -> dict[str, Any]:
    """Safe read shape for the API — never echoes the full api_key."""
    cfg = get_llm_config()
    key = cfg["api_key"] or ""
    return {
        "mode": cfg["mode"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key_set": bool(key),
        "api_key_hint": f"••••{key[-4:]}" if key else None,
    }


def update_llm_config(provided: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial update (only keys present in `provided`) and reset gateway.

    Raising here with a clear code gives the settings UI actionable feedback on
    invalid combinations (e.g. openai without a base URL).
    """
    cur = get_llm_config()

    if "mode" in provided:
        mode = provided["mode"]
        if mode not in _MODE_CHOICES:
            raise ValidationError(f"不支持的 LLM 模式：{mode}", {"mode": mode})
        cur["mode"] = mode

    if "base_url" in provided:
        cur["base_url"] = (provided["base_url"] or "").strip() or None
    if "api_key" in provided:
        cur["api_key"] = (provided["api_key"] or "").strip() or None
    if "model" in provided:
        cur["model"] = (provided["model"] or "").strip() or None

    if cur["mode"] == "openai" and not cur["base_url"]:
        raise ValidationError("LLM 模式为 openai 时必须提供 Base URL。", {"mode": cur["mode"]})

    # 只持久化明确设置的覆盖项；空值按"未设置"回落到环境变量。
    overrides = {
        key: value
        for key, value in {
            "mode": cur["mode"],
            "base_url": cur["base_url"],
            "api_key": cur["api_key"],
            "model": cur["model"],
        }.items()
        if value not in (None, "")
    }
    _write(overrides)

    # 让下次 factory.create_gateway() 用新配置重建（旧实例作废）。
    from app.llm.factory import reset_gateway

    reset_gateway()
    return get_config_read()


# ----------------------------------------------------------------- test/models --
# 连通性测试与模型列表（业界标配：保存前 test、GET {base}/models 拉模型下拉）。
# 探测走 httpx 直连 OpenAI 兼容端点，不经过 LangChain —— 保持 test 轻量可控。

import httpx  # noqa: E402  (module-level import kept near its only consumer group)

_PROBE_TIMEOUT = 6.0
_PING_TIMEOUT = 12.0
# 直连探测（trust_env=False）：base_url 是用户显式配置的端点，常为本地服务
# （Ollama/vLLM）；跟随系统代理会把回环地址也劫持成 502，混淆连接语义。
_CLIENT_KWARGS = {"timeout": _PROBE_TIMEOUT, "trust_env": False}


def _resolve_target(provided: dict[str, Any] | None) -> dict[str, Any]:
    """Merge an optional partial override (from the request body) over saved config."""
    cfg = get_llm_config()
    for key in ("base_url", "api_key", "model"):
        value = (provided or {}).get(key)
        if value:
            cfg[key] = value.strip()
    return cfg


def _auth_headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _probe_models(base_url: str, api_key: str | None) -> tuple[int, list[str]]:
    """GET {base_url}/models → (status, model ids). Raises nothing (transport → -1)."""
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(**_CLIENT_KWARGS) as client:
            resp = await client.get(url, headers=_auth_headers(api_key))
    except httpx.HTTPError:
        return -1, []
    ids: list[str] = []
    if resp.status_code == 200:
        try:
            data = resp.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            ids = [str(item.get("id") or item) for item in items if isinstance(item, (dict, str))]
        except ValueError:
            ids = []
    return resp.status_code, ids


async def _chat_ping(base_url: str, api_key: str | None, model: str | None) -> tuple[int, str]:
    """Minimal chat completion fallback for endpoints without /models."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model or "default",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=_PING_TIMEOUT, trust_env=False) as client:
            resp = await client.post(url, headers=_auth_headers(api_key), json=payload)
    except httpx.HTTPError as exc:
        return -1, f"无法连接 {base_url}：{exc.__class__.__name__}"
    if resp.status_code == 200:
        return 200, "ok"
    detail = ""
    try:
        detail = str(resp.json().get("error", {}).get("message", ""))[:200]
    except ValueError:
        detail = resp.text[:200]
    return resp.status_code, detail or f"HTTP {resp.status_code}"


async def test_llm_connection(provided: dict[str, Any] | None = None) -> dict[str, Any]:
    """Probe the (possibly unsaved) connection. Never raises — mirrors
    /providers/comfyui/test shape: 200 + {connected, latency_ms, error?}."""
    import time

    cfg = _resolve_target(provided)
    # fake 且没有指向真实端点的探测参数（未保存的 base_url）→ 无需连接。
    # 反之（mode=fake 但测试新 base_url）按 openai 探测，服务于「先测再切」。
    if cfg["mode"] == "fake" and not (provided and provided.get("base_url")):
        return {"connected": True, "mode": "fake", "latency_ms": 0, "detail": "fake 模式无需连接（确定性规则输出）"}

    base_url = cfg.get("base_url")
    if not base_url:
        return {"connected": False, "mode": "openai", "error": "缺少 Base URL，无法测试。"}

    started = time.perf_counter()
    status, ids = await _probe_models(base_url, cfg.get("api_key"))
    latency_ms = int((time.perf_counter() - started) * 1000)

    if status == 200:
        return {
            "connected": True,
            "mode": "openai",
            "latency_ms": latency_ms,
            "models_count": len(ids),
            "sample_models": ids[:8],
            "detail": "GET /models 探测通过",
        }
    if status in (401, 403):
        return {"connected": False, "mode": "openai", "latency_ms": latency_ms, "error": f"鉴权失败（HTTP {status}），请检查 API Key。"}

    # /models 不可用（404/405/网关不支持）或网络失败 → 降级最小 chat 探测。
    ping_status, detail = await _chat_ping(base_url, cfg.get("api_key"), cfg.get("model"))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if ping_status == 200:
        return {"connected": True, "mode": "openai", "latency_ms": latency_ms, "detail": "chat 探测通过（端点未提供 /models）"}
    return {
        "connected": False,
        "mode": "openai",
        "latency_ms": latency_ms if ping_status != -1 else None,
        "error": detail or f"探测失败（models HTTP {status} / ping HTTP {ping_status}）",
    }


async def list_llm_models() -> list[str]:
    """Model ids from the SAVED openai-compatible endpoint (for the settings dropdown).

    fake mode returns the deterministic placeholder; openai failures raise
    ProviderUnavailableError so the UI can fall back to free-text input.
    """
    from app.core.errors import ProviderUnavailableError

    cfg = get_llm_config()
    if cfg["mode"] == "fake":
        return ["fake-chat"]
    base_url = cfg.get("base_url")
    if not base_url:
        raise ProviderUnavailableError("缺少 Base URL，无法拉取模型列表。", {})
    status, ids = await _probe_models(base_url, cfg.get("api_key"))
    if status == 200 and ids:
        return ids
    raise ProviderUnavailableError(
        f"模型列表拉取失败（HTTP {status}）。请检查连接后重试，或直接手动输入模型名。",
        {"base_url": base_url, "status": status},
    )
