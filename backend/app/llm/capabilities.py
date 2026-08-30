"""Per-model capability heuristics — advisory metadata, never a hard gate.

模型名启发式（业界通用做法）：给 UI / 运行时一个"这个连接大概率能做什么"的标记
（tools / vision / reasoning）。两点设计约束：

1. **Advisory only**：启发式错了也绝不阻塞可用连接 —— 真实能力以实际调用为准。
2. **Override wins**：profile 上可显式声明 capabilities，用户声明优先于启发式
   （启发式覆盖不到的私有部署/新模型由用户兜底）。

fake 模式没有真实模型，能力全 False。
"""

from __future__ import annotations

import re

_CAP_KEYS = ("tools", "vision", "reasoning")

# 视觉输入（image in → text out）的常见命名片段。
_VISION_PATTERNS = (
    r"gpt-4o",
    r"gpt-4\.1",
    r"gpt-5",
    r"chatgpt-4o",
    r"glm-4v",
    r"qvq",
    r"qwen.*-vl",
    r"llava",
    r"internvl",
    r"gemini",
    r"claude-(3|4)",
    r"pixtral",
    r"moondream",
    r"minicpm-v",
    r"vision",
)

# 已知不支持（或历史上不支持）function calling 的模型家族。
_NO_TOOLS_PATTERNS = (
    r"o1-(preview|mini|pro)",
    r"deepseek-reasoner",  # R1 系推理通道；advisory —— 若厂商后续支持可用 override 打开
)

# 推理链（thinking / reasoner）家族。
_REASONING_PATTERNS = (
    r"\bo[134](-|\b)",
    r"deepseek-r1",
    r"deepseek-reasoner",
    r"qwq",
    r"thinking",
    r"-r1\b",
)


def _matches(name: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, name) for p in patterns)


def model_capabilities(
    model: str | None,
    *,
    mode: str = "openai",
    override: dict | None = None,
) -> dict:
    """Best-effort capability flags for a model id, merged with an optional
    explicit per-profile override. Returns {"tools", "vision", "reasoning", "source"}.
    """
    if mode == "fake":
        caps = {"tools": False, "vision": False, "reasoning": False, "source": "heuristic"}
        return caps
    name = (model or "").lower()
    caps = {
        "tools": not _matches(name, _NO_TOOLS_PATTERNS),
        "vision": _matches(name, _VISION_PATTERNS),
        "reasoning": _matches(name, _REASONING_PATTERNS),
        "source": "heuristic",
    }
    if override:
        explicit = {k: bool(v) for k, v in override.items() if k in _CAP_KEYS and v is not None}
        if explicit:
            caps.update(explicit)
            caps["source"] = "override"
    return caps
