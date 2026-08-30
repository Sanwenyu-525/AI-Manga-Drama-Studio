"""Runtime LLM connection management: 多连接 Profile Registry + 任务级绑定.

分层（P-LLM-Profiles）：
- env（app.core.config.Settings）→  {data_dir}/llm.json 覆盖层：**仅作引导种子**。
  首次读取 Profile Registry 时把两者合并播种成「默认连接」，此后
  {data_dir}/llm_profiles.json 是唯一事实源，llm.json 不再参与解析。
- **api_key 安全策略：env（STUDIO_LLM_API_KEY）优先于磁盘明文**（llm.json /
  llm_profiles.json）。磁盘上的 key 仅作兜底——配置了 env 后即使磁盘残留
  明文也**永不生效**；profile_read 的掩码 hint 也以生效 key 为准。
- Profiles：命名连接（name/mode/base_url/api_key/model/capabilities），多份共存，
  UI 可切换激活；每个任务（director/script/continuity）可绑定到任意连接，
  未绑定的任务跟随激活连接。
- 更新任何连接/绑定都会重置 gateway 缓存，下次 AI 调用即用新配置（无需重启）。

This is connection plumbing only — it never stores any project content, so it is
not "Project State" (AGENTS §3 rule 11).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError

LLM_CONFIG_FILE = "llm.json"  # legacy 引导层（env 兜底）
LLM_PROFILES_FILE = "llm_profiles.json"  # 多连接 Profile Registry（权威源）
_MODE_CHOICES = ("fake", "openai")

# LLM 任务面：default=激活连接兜底；其余三个任务可单独绑定连接。
LLM_TASKS = ("default", "director", "script", "continuity")
LLM_BINDABLE_TASKS = ("director", "script", "continuity")
_TASK_LABELS = {
    "director": "AI 导演",
    "script": "剧本分析 / 分镜",
    "continuity": "连续性检查",
}


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
    """Effective default-task LLM config (= the active profile). Legacy entry kept
    for factory / registry / probe call sites."""
    return get_task_llm_config("default")


def get_task_llm_config(task: str = "default") -> dict[str, Any]:
    """Resolve the connection a task should use: its binding → the active profile."""
    if task not in LLM_TASKS:
        raise ValidationError(
            f"未知的 LLM 任务：{task}", {"task": task, "supported": list(LLM_TASKS)}
        )
    state = _load_state()
    profile: dict[str, Any] | None = None
    if task != "default":
        bound_id = state["task_bindings"].get(task)
        if bound_id:
            profile = _find_profile(state, bound_id)
    if profile is None:
        profile = _find_profile(state, state["active_profile_id"])
    if profile is None and state["profiles"]:
        profile = state["profiles"][0]
    if profile is None:
        # Registry 为空（极端情况）：回落引导配置，保证业务不断链。
        cfg = _legacy_llm_config()
        cfg.update({"profile_id": None, "profile_name": None})
        return cfg
    return {
        "mode": profile["mode"],
        "base_url": profile.get("base_url"),
        # env 优先：STUDIO_LLM_API_KEY 设置后 profile 磁盘明文永不生效。
        "api_key": settings.llm_api_key or profile.get("api_key"),
        "model": profile.get("model"),
        "profile_id": profile["id"],
        "profile_name": profile.get("name"),
    }


def get_config_read() -> dict[str, Any]:
    """Safe read shape for the API — never echoes the full api_key."""
    cfg = get_llm_config()
    key = cfg.get("api_key") or ""
    capabilities = None
    profile_id = cfg.get("profile_id")
    if profile_id:
        profile = _find_profile(_load_state(), profile_id)
        if profile is not None:
            from app.llm.capabilities import model_capabilities

            capabilities = model_capabilities(
                profile.get("model"), mode=profile["mode"], override=profile.get("capabilities")
            )
    return {
        "mode": cfg.get("mode", "fake"),
        "base_url": cfg.get("base_url"),
        "model": cfg.get("model"),
        "api_key_set": bool(key),
        "api_key_hint": f"••••{key[-4:]}" if key else None,
        "profile_id": profile_id,
        "profile_name": cfg.get("profile_name"),
        "capabilities": capabilities,
    }


def update_llm_config(provided: dict[str, Any]) -> dict[str, Any]:
    """Legacy single-connection entry (PUT /llm/config): update the ACTIVE profile.

    Raising here with a clear code gives the settings UI actionable feedback on
    invalid combinations (e.g. openai without a base URL).
    """
    state = _load_state()
    return update_llm_profile(state["active_profile_id"], provided)


# ------------------------------------------------------------- profile registry --
# 多连接命名 Profile（P-LLM-Profiles）。存储即契约：{profiles, active_profile_id,
# task_bindings}；api_key 以明文落本机数据目录（与 legacy llm.json 同级安全性），
# 任何读取形状都必须走掩码（_profile_read / get_config_read）。


def _profiles_path() -> Path:
    return settings.data_dir / LLM_PROFILES_FILE


def _read_profiles_raw() -> dict[str, Any] | None:
    p = _profiles_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
        return None
    return data


def _find_profile(state: dict[str, Any], profile_id: str | None) -> dict[str, Any] | None:
    if not profile_id:
        return None
    return next((p for p in state["profiles"] if p.get("id") == profile_id), None)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _legacy_llm_config() -> dict[str, Any]:
    """env defaults + optional llm.json layer（引导播种专用；api_key 安全策略：env 优先）。"""
    over = _read_overrides()
    mode = over.get("mode") if over.get("mode") in _MODE_CHOICES else settings.llm_mode
    return {
        "mode": mode,
        "base_url": (over.get("base_url") or None) or settings.llm_base_url,
        # env 优先：STUDIO_LLM_API_KEY 设置后磁盘明文（llm.json）永不生效。
        "api_key": settings.llm_api_key or (over.get("api_key") or None),
        "model": (over.get("model") or None) or settings.llm_model,
    }


def _seed_state() -> dict[str, Any]:
    """首次使用：把 env + llm.json 的生效配置播种成「默认连接」（不落盘，仅内存视图）。"""
    cfg = _legacy_llm_config()
    return {
        "profiles": [
            {
                "id": "default",
                "name": "默认连接",
                "mode": cfg["mode"],
                "base_url": cfg["base_url"],
                "api_key": cfg["api_key"],
                "model": cfg["model"],
                "capabilities": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
        ],
        "active_profile_id": "default",
        "task_bindings": {},
        "task_fallbacks": {},
    }


def _load_state() -> dict[str, Any]:
    raw = _read_profiles_raw()
    if raw is None:
        return _seed_state()
    bindings = {
        task: pid
        for task, pid in (raw.get("task_bindings") or {}).items()
        if task in LLM_BINDABLE_TASKS and isinstance(pid, str)
    }
    known_ids = {p.get("id") for p in raw["profiles"] if isinstance(p, dict)}
    fallbacks = {}
    for task, pids in (raw.get("task_fallbacks") or {}).items():
        if task not in LLM_BINDABLE_TASKS or not isinstance(pids, list):
            continue
        # 只保留仍存在的连接（防手工编辑文件产生悬空引用）；去重保序。
        fallbacks[task] = list(dict.fromkeys(pid for pid in pids if pid in known_ids))
    return {
        "profiles": [p for p in raw["profiles"] if isinstance(p, dict) and p.get("id")],
        "active_profile_id": raw.get("active_profile_id") or "default",
        "task_bindings": bindings,
        "task_fallbacks": fallbacks,
    }


def _save_state(state: dict[str, Any]) -> None:
    path = _profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    # 任何连接/绑定变更都让 gateway 缓存作废，下次调用按新配置重建。
    from app.llm.factory import reset_gateway

    reset_gateway()


def _validate_connection_fields(mode: str, base_url: str | None) -> None:
    if mode not in _MODE_CHOICES:
        raise ValidationError(f"不支持的 LLM 模式：{mode}", {"mode": mode})
    if mode == "openai" and not base_url:
        raise ValidationError("LLM 模式为 openai 时必须提供 Base URL。", {"mode": mode})


def _profile_read(state: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    from app.llm.capabilities import model_capabilities

    # 生效 key = env 优先于 profile 磁盘明文（安全策略，与 get_task_llm_config 一致）。
    key = settings.llm_api_key or (profile.get("api_key") or "")
    override = profile.get("capabilities")
    return {
        "id": profile["id"],
        "name": profile.get("name") or profile["id"],
        "mode": profile["mode"],
        "base_url": profile.get("base_url"),
        "model": profile.get("model"),
        "api_key_set": bool(key),
        "api_key_hint": f"••••{key[-4:]}" if key else None,
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
        "is_active": profile["id"] == state["active_profile_id"],
        "bound_tasks": sorted(
            task for task, pid in state["task_bindings"].items() if pid == profile["id"]
        ),
        "capabilities": model_capabilities(
            profile.get("model"), mode=profile["mode"], override=override
        ),
    }


def list_llm_profiles() -> dict[str, Any]:
    state = _load_state()

    def _binding_read(pid: str | None) -> dict[str, str] | None:
        profile = _find_profile(state, pid)
        return {"profile_id": pid, "profile_name": profile.get("name")} if profile else None

    bindings = {task: _binding_read(state["task_bindings"].get(task)) for task in LLM_BINDABLE_TASKS}
    fallbacks = {
        task: [
            read
            for pid in state["task_fallbacks"].get(task, [])
            if (read := _binding_read(pid)) is not None
        ]
        for task in LLM_BINDABLE_TASKS
    }
    return {
        "profiles": [_profile_read(state, p) for p in state["profiles"]],
        "active_profile_id": state["active_profile_id"],
        "task_bindings": bindings,
        "task_fallbacks": fallbacks,
        "tasks": [{"id": task, "label": _TASK_LABELS[task]} for task in LLM_BINDABLE_TASKS],
    }


def create_llm_profile(data: dict[str, Any]) -> dict[str, Any]:
    state = _load_state()
    mode = (data.get("mode") or "fake").strip()
    base_url = (data.get("base_url") or "").strip() or None
    _validate_connection_fields(mode, base_url)
    profile = {
        "id": f"prof_{uuid.uuid4().hex[:10]}",
        "name": (data.get("name") or "").strip() or f"连接 {len(state['profiles']) + 1}",
        "mode": mode,
        "base_url": base_url,
        "api_key": (data.get("api_key") or "").strip() or None,
        "model": (data.get("model") or "").strip() or None,
        "capabilities": data.get("capabilities") if isinstance(data.get("capabilities"), dict) else None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    state["profiles"].append(profile)
    _save_state(state)
    return _profile_read(state, profile)


def update_llm_profile(profile_id: str, provided: dict[str, Any]) -> dict[str, Any]:
    """Partial update — only keys present in `provided` change; empty api_key/base_url
    clears the stored value."""
    state = _load_state()
    profile = _find_profile(state, profile_id)
    if profile is None:
        raise NotFoundError("LLM 连接不存在。", {"profile_id": profile_id})

    candidate = dict(profile)
    if "mode" in provided:
        candidate["mode"] = (provided["mode"] or "").strip()
    if "base_url" in provided:
        candidate["base_url"] = (provided["base_url"] or "").strip() or None
    if "api_key" in provided:
        candidate["api_key"] = (provided["api_key"] or "").strip() or None
    if "model" in provided:
        candidate["model"] = (provided["model"] or "").strip() or None
    if "name" in provided:
        candidate["name"] = (provided["name"] or "").strip() or profile.get("name")
    if "capabilities" in provided:
        candidate["capabilities"] = (
            provided["capabilities"] if isinstance(provided["capabilities"], dict) else None
        )
    _validate_connection_fields(candidate["mode"], candidate.get("base_url"))

    profile.update(candidate)
    profile["updated_at"] = _now()
    _save_state(state)
    return _profile_read(state, profile)


def activate_llm_profile(profile_id: str) -> dict[str, Any]:
    state = _load_state()
    profile = _find_profile(state, profile_id)
    if profile is None:
        raise NotFoundError("LLM 连接不存在。", {"profile_id": profile_id})
    state["active_profile_id"] = profile_id
    _save_state(state)
    return _profile_read(state, profile)


def delete_llm_profile(profile_id: str) -> dict[str, Any]:
    state = _load_state()
    profile = _find_profile(state, profile_id)
    if profile is None:
        raise NotFoundError("LLM 连接不存在。", {"profile_id": profile_id})
    if profile_id == state["active_profile_id"]:
        raise ValidationError(
            "不能删除当前激活的连接，请先切换到其他连接。",
            {"profile_id": profile_id, "active_profile_id": state["active_profile_id"]},
        )
    state["profiles"] = [p for p in state["profiles"] if p.get("id") != profile_id]
    state["task_bindings"] = {
        task: pid for task, pid in state["task_bindings"].items() if pid != profile_id
    }
    state["task_fallbacks"] = {
        task: [pid for pid in pids if pid != profile_id]
        for task, pids in state.get("task_fallbacks", {}).items()
    }
    _save_state(state)
    return {"deleted": profile_id}


def set_task_bindings(bindings: dict[str, Any]) -> dict[str, Any]:
    """task → profile_id（None 解绑跟随激活连接）。未知任务/连接一律 422。"""
    state = _load_state()
    for task, pid in bindings.items():
        if task not in LLM_BINDABLE_TASKS:
            raise ValidationError(
                f"任务 {task} 不支持绑定连接。",
                {"task": task, "supported": list(LLM_BINDABLE_TASKS)},
            )
        if pid is not None and _find_profile(state, pid) is None:
            raise ValidationError("绑定目标连接不存在。", {"task": task, "profile_id": pid})
    for task, pid in bindings.items():
        if pid is None:
            state["task_bindings"].pop(task, None)
        else:
            state["task_bindings"][task] = pid
    _save_state(state)
    return list_llm_profiles()


def set_task_fallbacks(fallbacks: dict[str, Any]) -> dict[str, Any]:
    """task → 有序降级连接列表（P-LLM-Fallback）。

    降级是显式配置：只有出现在这里 ordered list 里的连接才会参与降级尝试；
    空列表 = 清除 = 该任务回到纯 fail-fast。未知任务/连接一律 422；列表内
    去重保序。default 任务即激活连接本身，不参与降级配置。
    """
    state = _load_state()
    for task, pids in fallbacks.items():
        if task not in LLM_BINDABLE_TASKS:
            raise ValidationError(
                f"任务 {task} 不支持配置降级链。",
                {"task": task, "supported": list(LLM_BINDABLE_TASKS)},
            )
        if not isinstance(pids, list) or any(not isinstance(pid, str) for pid in pids):
            raise ValidationError("降级链必须是有序的连接 id 列表。", {"task": task})
        for pid in pids:
            if _find_profile(state, pid) is None:
                raise ValidationError("降级链中的连接不存在。", {"task": task, "profile_id": pid})
    for task, pids in fallbacks.items():
        state["task_fallbacks"][task] = list(dict.fromkeys(pids))
    _save_state(state)
    return list_llm_profiles()


def get_task_llm_chain(task: str = "default") -> list[dict[str, Any]]:
    """Ordered failover candidates for a task（factory 降级链构建的数据源）。

    链 = 主连接（绑定连接；未绑定任务则用激活连接）+ 显式配置的降级连接。
    已绑定任务的激活连接**不会**隐式入链 —— 链上只有用户配置过的东西
    （不静默掩盖原则：没有未声明的候选）。
    """
    if task not in LLM_TASKS:
        raise ValidationError(
            f"未知的 LLM 任务：{task}", {"task": task, "supported": list(LLM_TASKS)}
        )
    state = _load_state()
    chain_ids: list[str] = []
    if task != "default":
        bound_id = state["task_bindings"].get(task)
        if bound_id:
            chain_ids.append(bound_id)
    if not chain_ids:
        chain_ids.append(state["active_profile_id"])
    for pid in state["task_fallbacks"].get(task, []):
        if pid not in chain_ids:
            chain_ids.append(pid)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pid in chain_ids:
        if pid in seen:
            continue
        profile = _find_profile(state, pid)
        if profile is None:
            continue
        seen.add(pid)
        candidates.append(
            {
                "profile_id": profile["id"],
                "profile_name": profile.get("name"),
                "mode": profile["mode"],
                "base_url": profile.get("base_url"),
                # env 优先：STUDIO_LLM_API_KEY 设置后 profile 磁盘明文永不生效。
                "api_key": settings.llm_api_key or profile.get("api_key"),
                "model": profile.get("model"),
            }
        )
    return candidates


# ----------------------------------------------------------------- test/models --
# 连通性测试与模型列表（业界标配：保存前 test、GET {base}/models 拉模型下拉）。
# 探测走 httpx 直连 OpenAI 兼容端点，不经过 LangChain —— 保持 test 轻量可控。

import httpx  # noqa: E402  (module-level import kept near its only consumer group)

import asyncio  # noqa: E402
import time  # noqa: E402

_PROBE_TIMEOUT = 6.0
_PING_TIMEOUT = 12.0
_DETECT_TIMEOUT = 1.0  # 本地端口探测要快：没监听的端口会立即拒绝，1s 足够
# 直连探测（trust_env=False）：base_url 是用户显式配置的端点，常为本地服务
# （Ollama/vLLM）；跟随系统代理会把回环地址也劫持成 502，混淆连接语义。
_CLIENT_KWARGS = {"timeout": _PROBE_TIMEOUT, "trust_env": False}

# 本机常见 OpenAI 兼容服务的默认端口（探测目标，按出现频率排列）。
_LOCAL_LLM_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("ollama", "Ollama", "http://127.0.0.1:11434/v1"),
    ("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1"),
    ("vllm", "vLLM", "http://127.0.0.1:8000/v1"),
    ("llamacpp", "llama.cpp server", "http://127.0.0.1:8080/v1"),
    ("jan", "Jan", "http://127.0.0.1:1337/v1"),
    ("koboldcpp", "KoboldCpp", "http://127.0.0.1:5001/v1"),
)


def _resolve_target(provided: dict[str, Any] | None) -> dict[str, Any]:
    """Merge an optional partial override (from the request body) over saved config.

    profile_id 先切换基准连接（测试某条已存连接），显式 base_url/api_key/model
    覆盖再叠加（test-before-save）。
    """
    cfg = get_llm_config()
    profile_id = (provided or {}).get("profile_id")
    if profile_id:
        profile = _find_profile(_load_state(), profile_id)
        if profile is None:
            raise NotFoundError("LLM 连接不存在。", {"profile_id": profile_id})
        cfg = {
            "mode": profile["mode"],
            "base_url": profile.get("base_url"),
            "api_key": profile.get("api_key"),
            "model": profile.get("model"),
        }
    for key in ("base_url", "api_key", "model"):
        value = (provided or {}).get(key)
        if value:
            cfg[key] = value.strip()
    return cfg


def _auth_headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _probe_models(
    base_url: str,
    api_key: str | None,
    *,
    # `timeout` 名称是既有探测 API（测试桩按 2 位置参数 mock 本函数，detect 传 kwarg）；
    # ASYNC109 嫌其与 asyncio 语义混淆，这里显式豁免。
    timeout: float = _PROBE_TIMEOUT,  # noqa: ASYNC109
) -> tuple[int, list[str]]:
    """GET {base_url}/models → (status, model ids). Raises nothing (transport → -1)."""
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
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


async def list_llm_models(profile_id: str | None = None) -> list[str]:
    """Model ids from the SAVED openai-compatible endpoint (for the settings dropdown).

    profile_id 指定某条连接（为未激活连接拉模型列表）；缺省用当前生效配置。
    fake mode returns the deterministic placeholder; openai failures raise
    ProviderUnavailableError so the UI can fall back to free-text input.
    """
    from app.core.errors import ProviderUnavailableError

    if profile_id:
        profile = _find_profile(_load_state(), profile_id)
        if profile is None:
            raise NotFoundError("LLM 连接不存在。", {"profile_id": profile_id})
        cfg: dict[str, Any] = {
            "mode": profile["mode"],
            "base_url": profile.get("base_url"),
            "api_key": profile.get("api_key"),
        }
    else:
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


async def detect_local_llm_servers() -> dict[str, Any]:
    """Probe common local OpenAI-compatible servers (Ollama / LM Studio / vLLM / ...).

    Concurrent GET {base}/models with a short timeout per candidate; only endpoints
    answering 200 are reported. Never raises — mirrors /llm/test conventions so the
    settings UI can render "nothing found" from data instead of an error.
    """
    started = time.perf_counter()
    probes = [
        _probe_models(base, None, timeout=_DETECT_TIMEOUT)
        for _, _, base in _LOCAL_LLM_CANDIDATES
    ]
    results = await asyncio.gather(*probes)
    servers: list[dict[str, Any]] = []
    for (kind, label, base), (status, ids) in zip(_LOCAL_LLM_CANDIDATES, results, strict=True):
        if status != 200:
            continue
        servers.append(
            {
                "kind": kind,
                "label": label,
                "base_url": base,
                "models_count": len(ids),
                "sample_models": ids[:8],
            }
        )
    return {"servers": servers, "latency_ms": int((time.perf_counter() - started) * 1000)}
