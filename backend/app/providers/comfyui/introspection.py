"""ComfyUIIntrospector — 检查通道的 native 实现（P2-E4-T02）。

数据源是 ComfyUI 自己的 GET /object_info（与生产通道同源，无第三方依赖）。
相对 get_catalog()（只探 5 个 Loader 节点的模型枚举），本实现按需投影
任意 class_types 的枚举输入，供 workflow live 诊断使用。
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.providers.comfyui.client import ComfyUIClient
from app.providers.workflow.introspection import EnvironmentSnapshot

logger = get_logger("comfyui.introspection")

# ComfyUI 用这些纯大写 token 声明输入类型（非枚举）——出现在
# ["INT", {...}] 这类形态里，不能当作可选值列表。
_TYPE_TOKENS = {"INT", "STRING", "FLOAT", "BOOLEAN", "NUMBER", "COMBO", "IMAGE", "LATENT", "MASK", "MODEL", "CLIP", "VAE", "CONDITIONING", "CONTROL_NET", "NOISE", "GUIDER", "SAMPLER", "SIGMAS", "UPSCALE_MODEL"}


def parse_enum_choices(raw: object) -> list[str] | None:
    """解析 ComfyUI object_info 的枚举输入为可选值列表；非枚举 → None。

    枚举两种形态：[["a","b"], {meta}] 或 ["a","b"]（全字符串）。
    含类型 token（如 ["INT", {...}]）的不是枚举。
    """
    if not isinstance(raw, list) or not raw:
        return None
    first = raw[0]
    if isinstance(first, list) and first and all(isinstance(x, str) for x in first):
        return first
    if all(isinstance(x, str) for x in raw):
        if any(x in _TYPE_TOKENS for x in raw):
            return None
        return raw
    return None


def project_choices(object_info: dict, class_types: list[str]) -> dict[str, dict[str, list[str]]]:
    """从全量 object_info 投影指定 class_types 的枚举输入。

    节点存在即登记（即使没有任何枚举输入也登记空 dict）——"缺节点"的判定
    依据是键缺失，而不是"没有枚举"。
    """
    result: dict[str, dict[str, list[str]]] = {}
    for class_type in class_types:
        spec = object_info.get(class_type)
        if not isinstance(spec, dict):
            continue  # 缺节点：结果中无该键
        inputs = spec.get("input") or {}
        choices: dict[str, list[str]] = {}
        for section in ("required", "optional"):
            for input_name, raw in (inputs.get(section) or {}).items():
                parsed = parse_enum_choices(raw)
                if parsed:
                    choices[input_name] = parsed
        result[class_type] = choices
    return result


class ComfyUIIntrospector:
    """WorkflowIntrospector 的 native 实现（无 MCP 依赖，诊断默认通道）。"""

    name = "native"

    def __init__(self, base_url: str | None = None, client: ComfyUIClient | None = None) -> None:
        self._client = client or ComfyUIClient(base_url)

    async def resolve_choices(self, class_types: list[str]) -> EnvironmentSnapshot:
        info = await self._client.get_object_info()
        if info is None:
            return EnvironmentSnapshot(
                reachable=False,
                source=self.name,
                error="ComfyUI unreachable (GET /object_info failed).",
            )
        if not isinstance(info, dict):
            return EnvironmentSnapshot(
                reachable=False, source=self.name, error="ComfyUI /object_info returned an unexpected shape."
            )
        choices = project_choices(info, class_types)
        return EnvironmentSnapshot(reachable=True, source=self.name, choices=choices, node_count=len(info))
