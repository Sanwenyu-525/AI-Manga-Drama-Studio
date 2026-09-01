"""Workflow live 诊断服务（P2-E4-T02 检查通道）.

双通道架构中"理解/诊断层"的 Application Service：
- validate_workflow_async：静态 preflight + live 校验（native 或 MCP
  introspector，STUDIO_COMFY_INTROSPECTION 选择；MCP 失败自动回落 native），
  供 API 端点 / 前端健康面板使用。
- validate_workflow_sync：同步原生通道（不走 MCP——同步上下文无法承载
  stdio 会话生命周期），供 create_generation fail-fast 与 Agent 工具使用
  （线程池 / 运行中事件循环内均不可 asyncio.run）。

红线：Agent 工具与 API 只经本 Service 访问检查通道；本 Service 只读，
永不下发 queue/interrupt（生产执行永远走 GenerationService → ImageProvider）。
"""

from __future__ import annotations

import time

from app.core.config import settings
from app.core.errors import ProviderUnavailableError, StudioError
from app.core.logging import get_logger
from app.providers.comfyui.introspection import ComfyUIIntrospector, project_choices
from app.providers.comfyui.mcp_introspection import ComfyMCPIntrospector
from app.providers.comfyui.workflow_mapper import WorkflowMapper
from app.providers.workflow.introspection import (
    DIAG_BROKEN_LINK,
    DIAG_MISSING_MODEL,
    DIAG_MISSING_NODE,
    DIAG_OK,
    WF_INVALID,
    WF_OK,
    WF_STATIC_ERROR,
    WF_UNREACHABLE,
    NodeDiagnosis,
    WorkflowDiagnostics,
    WorkflowIntrospector,
)

logger = get_logger("workflow.diagnostics")

# object_info 可达 MB 级：原始快照按 base_url 缓存 60s（MCP 通道不缓存——
# stdio 会话生命周期即调用，缓存会掩盖工具面漂移）。
SNAPSHOT_TTL_SECONDS = 60.0


def template_node_classes(template: dict) -> list[str]:
    return [
        node.get("class_type")
        for node in template.values()
        if isinstance(node, dict) and isinstance(node.get("class_type"), str)
    ]


class WorkflowDiagnosticsService:
    """检查通道的唯一入口（API + Agent 工具都经此，红线合规）。"""

    def __init__(self, introspector: WorkflowIntrospector | None = None) -> None:
        self._introspector_override = introspector
        # base_url -> (monotonic, raw object_info | None)
        self._async_cache: dict[str, tuple[float, dict | None]] = {}
        self._sync_cache: dict[str, tuple[float, dict | None]] = {}

    # --- introspector 选择（native ⇄ mcp，MCP 失败回落 native） ---

    def _build_introspector(self, base_url: str | None) -> WorkflowIntrospector:
        if self._introspector_override is not None:
            return self._introspector_override
        if settings.comfy_introspection == "mcp":
            try:
                return ComfyMCPIntrospector()
            except ProviderUnavailableError as exc:
                logger.warning("mcp introspector unavailable, falling back to native: %s", exc.message)
        return ComfyUIIntrospector(base_url)

    # --- live 校验（async：API 端点 / 前端面板） ---

    async def validate_workflow_async(
        self, workflow_id: str | None = None, base_url: str | None = None
    ) -> WorkflowDiagnostics:
        mapper = WorkflowMapper(workflow_id=workflow_id)
        try:
            template = mapper.load_template()  # 静态 preflight（JSON/输出节点/schema 契约）
        except StudioError as exc:
            return WorkflowDiagnostics(
                workflow_id=mapper.workflow_id, status=WF_STATIC_ERROR, static_error=exc.message
            )

        try:
            choices, source, error = await self._live_choices_async(base_url, template_node_classes(template))
        except Exception as exc:  # noqa: BLE001 — 诊断永不向调用方抛（红线：检查通道降级不阻断）
            logger.warning("live diagnostics crashed: %s", exc)
            choices, source, error = None, None, f"diagnostics crashed: {exc}"
        if choices is None:
            # 无法完成 live 校验 → 不阻断排队（worker 运行时诚实失败）。
            return WorkflowDiagnostics(
                workflow_id=mapper.workflow_id, status=WF_UNREACHABLE, source=source, error=error
            )
        return self._diagnose(mapper.workflow_id, template, choices, source)

    # --- live 校验（sync：create_generation fail-fast / Agent 工具） ---

    def validate_workflow_sync(
        self, workflow_id: str | None = None, base_url: str | None = None
    ) -> WorkflowDiagnostics:
        mapper = WorkflowMapper(workflow_id=workflow_id)
        try:
            template = mapper.load_template()
        except StudioError as exc:
            return WorkflowDiagnostics(
                workflow_id=mapper.workflow_id, status=WF_STATIC_ERROR, static_error=exc.message
            )

        from app.providers.comfyui.client import ComfyUIClient

        client = ComfyUIClient(base_url)
        info = self._cached(self._sync_cache, client.base_url, client.get_object_info_sync)
        if info is None:
            return WorkflowDiagnostics(
                workflow_id=mapper.workflow_id,
                status=WF_UNREACHABLE,
                source="native",
                error="ComfyUI unreachable (GET /object_info failed).",
            )
        choices = project_choices(info, template_node_classes(template))
        return self._diagnose(mapper.workflow_id, template, choices, "native")

    # --- live 投影获取 ---

    async def _live_choices_async(
        self, base_url: str | None, class_types: list[str]
    ) -> tuple[dict[str, dict[str, list[str]]] | None, str, str | None]:
        """→ (choices, source, error)。choices=None 表示无法完成 live 校验。"""
        introspector = self._build_introspector(base_url)
        if isinstance(introspector, ComfyUIIntrospector):
            # native（注入或默认构建）：经其 client 取 TTL 缓存的全量 object_info，
            # 再按需投影——缓存绑定 client.base_url。
            client = introspector._client
            info = await self._cached_async(client.base_url, client.get_object_info)
            if info is None:
                return None, "native", "ComfyUI unreachable (GET /object_info failed)."
            return project_choices(info, class_types), "native", None
        try:
            snapshot = await introspector.resolve_choices(class_types)
        except ProviderUnavailableError as exc:
            logger.warning("mcp introspection unavailable, falling back to native: %s", exc.message)
            return await self._native_choices_async(base_url, class_types), "native", None
        if not snapshot.reachable:
            return None, snapshot.source, snapshot.error or "comfy-mcp introspection failed."
        return snapshot.choices, snapshot.source, snapshot.error

    async def _native_choices_async(
        self, base_url: str | None, class_types: list[str]
    ) -> dict[str, dict[str, list[str]]] | None:
        """MCP 回落路径的 native 投影。"""
        from app.providers.comfyui.client import ComfyUIClient

        client = ComfyUIClient(base_url)
        info = await self._cached_async(client.base_url, client.get_object_info)
        if info is None:
            return None
        return project_choices(info, class_types)

    # --- 诊断核心（纯函数，供 async/sync 两路共用） ---

    def _diagnose(
        self,
        workflow_id: str,
        template: dict,
        choices: dict[str, dict[str, list[str]]],
        source: str,
    ) -> WorkflowDiagnostics:
        """逐节点诊断：缺节点 / 缺模型（枚举越界）/ 断链。"""
        nodes: list[NodeDiagnosis] = []
        missing_nodes: list[str] = []
        missing_models: list[str] = []
        broken_links: list[str] = []

        for node_id, node in template.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            if not isinstance(class_type, str):
                continue
            specs = choices.get(class_type)
            if specs is None:
                nodes.append(
                    NodeDiagnosis(
                        node_id=node_id,
                        class_type=class_type,
                        status=DIAG_MISSING_NODE,
                        detail="Node class is not installed on the connected ComfyUI.",
                    )
                )
                missing_nodes.append(class_type)
                continue

            node_status = DIAG_OK
            node_missing: list[str] = []
            detail: str | None = None
            inputs = node.get("inputs", {})
            if isinstance(inputs, dict):
                for input_name, value in inputs.items():
                    if isinstance(value, list):
                        # API-format 连线：["<target_node_id>", output_index]
                        if value and str(value[0]) not in template:
                            broken_links.append(f"{node_id}.{input_name} -> {value[0]!r}")
                            node_status = DIAG_BROKEN_LINK
                            detail = detail or f"Input {input_name} links to a missing node."
                        continue
                    if not isinstance(value, str) or value.startswith("$"):
                        # $PROMPT 等占位符在 build 时注入（含 LoadImage 参考图
                        # 槽位），不属于 live 可校验的枚举值。
                        continue
                    available = specs.get(input_name)
                    if available and value not in available:
                        node_missing.append(value)
                        missing_models.append(f"{value} ({class_type}.{input_name})")
                        node_status = DIAG_MISSING_MODEL
                        detail = detail or f"Input {input_name}: {value!r} is not available on the server."
            nodes.append(
                NodeDiagnosis(
                    node_id=node_id,
                    class_type=class_type,
                    status=node_status,
                    detail=detail,
                    missing_choices=node_missing,
                )
            )

        status = WF_INVALID if (missing_nodes or missing_models or broken_links) else WF_OK
        return WorkflowDiagnostics(
            workflow_id=workflow_id,
            status=status,
            source=source,
            nodes=nodes,
            missing_nodes=sorted(set(missing_nodes)),
            missing_models=missing_models,
            broken_links=broken_links,
        )

    # --- 缓存 ---

    def _cached(self, cache: dict, key: str, fetch):
        cached = cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < SNAPSHOT_TTL_SECONDS:
            return cached[1]
        info = fetch()
        cache[key] = (now, info)
        return info

    async def _cached_async(self, key: str, fetch) -> dict | None:
        cached = self._async_cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < SNAPSHOT_TTL_SECONDS:
            return cached[1]
        info = await fetch()
        self._async_cache[key] = (now, info)
        return info

    def invalidate(self) -> None:
        """测试/用户显式刷新用：清空两级快照缓存。"""
        self._async_cache.clear()
        self._sync_cache.clear()


# 模块级单例（同 provider_health_service 模式）。
_diagnostics_service = WorkflowDiagnosticsService()


def get_workflow_diagnostics_service() -> WorkflowDiagnosticsService:
    return _diagnostics_service


def reset_workflow_diagnostics() -> None:
    _diagnostics_service.invalidate()
