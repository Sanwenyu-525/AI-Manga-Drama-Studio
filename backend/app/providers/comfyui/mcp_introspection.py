"""ComfyMCPIntrospector — 检查通道的 MCP 实现（P2-E4-T02 Phase 3）。

经由用户自装的官方 comfy-mcp（beta，AGPL-3.0-or-later OR Comfy commercial
license 双许可）做只读 introspection。设计约束：

- **不随应用分发、不进依赖硬绑定**：mcp sdk 延迟导入，comfy-mcp 由用户
  自行 pip install（STUDIO_COMFY_MCP_COMMAND 指向其 console script）；
  缺失时抛 ProviderUnavailableError，诊断服务回落 native。
- **beta 工具面不稳定**：工具名按名称模式动态匹配（node + search/info/
  describe...），入参从工具 inputSchema 的首个 string 属性推导，解析结果
  走宽容 walker——工具更名时降级报错而不是崩。
- **只读红线**：仅调用 introspection 类工具；run/generate/管理类工具本
  通道永不触达（红线 3/8——生产执行永远走 GenerationService 通道）。
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.comfyui.introspection import parse_enum_choices
from app.providers.workflow.introspection import EnvironmentSnapshot

logger = get_logger("comfyui.mcp_introspection")

# 节点检索类工具的名称模式（beta 期名称可能漂移，按语义匹配而非精确名）。
_NODE_TOOL_HINTS = ("search", "info", "describe", "detail", "find", "list")
_MCP_CONNECT_TIMEOUT = 30.0
_MCP_CALL_TIMEOUT = 60.0


def extract_node_found(obj: Any) -> bool:
    """宽容 walker：判断 MCP 返回的 JSON 里是否出现了节点 spec（存在性证据）。"""
    if isinstance(obj, dict):
        if isinstance(obj.get("input"), dict) or "class_type" in obj:
            return True
        return any(extract_node_found(v) for v in obj.values())
    if isinstance(obj, list):
        return any(extract_node_found(item) for item in obj)
    return False


def extract_node_choices(obj: Any) -> dict[str, list[str]]:
    """宽容 walker：在 comfy-mcp 返回的任意 JSON 里找节点 spec 并投影枚举输入。

    识别特征：含 "input" 且其下有 required/optional dict 的 dict（与
    object_info 同构）。取第一个匹配即止——检索结果里通常只有一个目标节点。
    """
    if isinstance(obj, dict):
        inputs = obj.get("input")
        if isinstance(inputs, dict):
            choices: dict[str, list[str]] = {}
            for section in ("required", "optional"):
                section_data = inputs.get(section)
                if not isinstance(section_data, dict):
                    continue
                for input_name, raw in section_data.items():
                    parsed = parse_enum_choices(raw)
                    if parsed:
                        choices[input_name] = parsed
            if choices:
                return choices
        for value in obj.values():
            found = extract_node_choices(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = extract_node_choices(item)
            if found:
                return found
    return {}


def _pick_tool(tools: list[Any], keywords: tuple[str, ...]) -> Any:
    """按名称语义匹配工具：必须含全部 keywords 且命中任一 hint。"""
    for tool in tools:
        name = getattr(tool, "name", "") or ""
        if all(k in name for k in keywords) and any(h in name for h in _NODE_TOOL_HINTS):
            return tool
    return None


def _pick_query_arg(tool: Any) -> str:
    """从工具 inputSchema 里挑首个 string 属性作为查询入参（beta 期参数名不稳定）。"""
    schema = getattr(tool, "inputSchema", None)
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    for key, spec in properties.items():
        if isinstance(spec, dict) and spec.get("type") == "string":
            return key
    return "query"


def _result_payload(result: Any) -> Any:
    """MCP CallToolResult → 可解析 payload（structuredContent 优先，回落 text JSON）。"""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    for content in getattr(result, "content", None) or []:
        text = getattr(content, "text", None)
        if text:
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return {"raw": text}
    return None


class ComfyMCPIntrospector:
    """WorkflowIntrospector 的 MCP 实现（comfy-mcp stdio，用户自装）。"""

    name = "mcp"

    def __init__(self, command: str | None = None) -> None:
        self._command = (command or settings.comfy_mcp_command).strip()

    async def resolve_choices(self, class_types: list[str]) -> EnvironmentSnapshot:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise ProviderUnavailableError(
                "mcp sdk 未安装（pip install mcp）——检查通道回落 native。",
            ) from exc

        params = StdioServerParameters(command=self._command)
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    node_tool = _pick_tool(listing.tools, ("node",))
                    if node_tool is None:
                        raise ProviderUnavailableError(
                            "comfy-mcp 未提供节点检索工具（beta 工具面已变更）——检查通道回落 native。"
                        )
                    arg_key = _pick_query_arg(node_tool)

                    choices: dict[str, dict[str, list[str]]] = {}
                    errors: list[str] = []
                    for class_type in class_types:
                        try:
                            result = await session.call_tool(node_tool.name, {arg_key: class_type})
                            if getattr(result, "isError", False):
                                errors.append(f"{class_type}: tool returned error")
                                continue
                            payload = _result_payload(result)
                            if extract_node_found(payload):
                                # 节点存在即登记（无枚举输入 → 空 dict，非缺节点）
                                choices[class_type] = extract_node_choices(payload)
                            # 检索不到 = 该实例无此节点（missing_node），不是错误。
                        except Exception as exc:  # noqa: BLE001 — 单节点查询失败不拖垮整体
                            errors.append(f"{class_type}: {exc}")
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — 连接失败必须降级而非崩
            raise ProviderUnavailableError(
                f"comfy-mcp ({self._command}) 连接失败：{exc} —— 检查通道回落 native。"
            ) from exc

        snapshot = EnvironmentSnapshot(
            reachable=True,
            source=self.name,
            choices=choices,
            # MCP 检索式通道拿不到全环境节点数——诚实留空。
            node_count=None,
        )
        if errors:
            # 部分节点无法核实：保留可达结果，但让服务层知道校验能力受限。
            snapshot.error = "部分节点经由 MCP 无法核实: " + "; ".join(errors)
            logger.warning("mcp introspection partial: %s", snapshot.error)
        return snapshot
