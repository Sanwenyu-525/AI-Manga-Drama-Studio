"""Workflow introspection contract (P2-E4-T02 检查通道).

红线 §7：外部实现（原生 ComfyUI HTTP / comfy-mcp MCP）必须先转成本模块的
Studio Domain Contract 再对外暴露。生产执行通道（GenerationService →
ImageProvider → ComfyUIClient）不经过本模块——检查通道只读，永不下发
queue/interrupt 类写操作（红线 3/8）。

双通道架构（ComfyUI API = 确定性生产执行层；检查通道 = 理解/诊断层）：
native 与 mcp 两个 WorkflowIntrospector 实现可互换，由
STUDIO_COMFY_INTROSPECTION 选择；MCP 缺失/能力不足时由诊断服务回落 native。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# node-level diagnosis status
DIAG_OK = "ok"
DIAG_MISSING_NODE = "missing_node"  # class_type 在该 ComfyUI 实例不存在（缺节点/缺 custom node）
DIAG_MISSING_MODEL = "missing_model"  # 枚举型输入（模型文件等）不在服务端可选列表里
DIAG_BROKEN_LINK = "broken_link"  # 输入连线指向模板中不存在的节点

# workflow-level status
WF_OK = "ok"  # 静态 + live 全部通过
WF_INVALID = "invalid"  # live 可达且发现确定性问题（可安全 422 的 fail-fast 依据）
WF_UNREACHABLE = "unreachable"  # 无法完成 live 校验（不阻断排队，worker 运行时诚实失败）
WF_STATIC_ERROR = "static_error"  # 模板静态缺陷（JSON 损坏 / 缺 SaveImage / 契约违约）


@dataclass
class EnvironmentSnapshot:
    """Live ComfyUI 环境的最小投影（仅诊断所需，绝不透传原始 object_info）。

    choices: class_type -> {input_name: 可选值列表}（仅枚举型输入）。
    请求的 class_types 中不存在的节点 = 在 choices 中无该键（即 missing_node）。
    """

    reachable: bool
    source: str  # "native" | "mcp"
    choices: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    node_count: int | None = None  # 全环境节点数（MCP 降级路径可为 None）
    error: str | None = None  # reachable=False 或校验能力受限时的原因


@dataclass
class NodeDiagnosis:
    node_id: str
    class_type: str
    status: str  # DIAG_*
    detail: str | None = None
    missing_choices: list[str] = field(default_factory=list)  # 缺失的枚举值（模型文件名等）


@dataclass
class WorkflowDiagnostics:
    workflow_id: str
    status: str  # WF_*
    source: str | None = None  # 完成校验的 introspector（native/mcp）
    nodes: list[NodeDiagnosis] = field(default_factory=list)
    missing_nodes: list[str] = field(default_factory=list)
    missing_models: list[str] = field(default_factory=list)  # "value (NodeClass.input)"
    broken_links: list[str] = field(default_factory=list)  # "node_id.input -> target"
    static_error: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == WF_OK

    def to_dict(self) -> dict[str, Any]:
        """API/Agent 契约序列化（前端健康面板 + Agent ToolResult.data 共用）。"""
        return {
            "workflow_id": self.workflow_id,
            "status": self.status,
            "source": self.source,
            "ok": self.ok,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "class_type": n.class_type,
                    "status": n.status,
                    "detail": n.detail,
                    "missing_choices": n.missing_choices,
                }
                for n in self.nodes
            ],
            "missing_nodes": list(self.missing_nodes),
            "missing_models": list(self.missing_models),
            "broken_links": list(self.broken_links),
            "static_error": self.static_error,
            "error": self.error,
        }


@runtime_checkable
class WorkflowIntrospector(Protocol):
    """检查通道 introspection 接口（契约化，红线 §7）。

    resolve_choices 是查询式（而非全量快照式）：调用方只需验证模板涉及
    的 class_types。这对 MCP 实现是关键——comfy-mcp 的节点检索是
    query-oriented 的，全量枚举语义在其 beta 工具面上不保证存在。
    """

    name: str

    async def resolve_choices(self, class_types: list[str]) -> EnvironmentSnapshot:
        """对给定 class_types 返回 {input_name: choices} 投影。

        不存在的节点：choices 中无该键。实现永不 raise——失败以
        reachable=False + error 表达，由诊断服务降级处理。
        """
        ...
