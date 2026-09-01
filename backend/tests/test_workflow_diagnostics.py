"""P2-E4-T02 检查通道 — workflow live 诊断（native + MCP 双实现）测试。

覆盖：
- ComfyUIClient.get_object_info / get_object_info_sync（MockTransport，never-raise）
- 枚举解析 / class_types 投影（parse_enum_choices / project_choices）
- WorkflowDiagnosticsService：ok / 缺节点 / 缺模型 / 断链 / unreachable / 静态缺陷
- create_generation fail-fast 422（invalid 拦截 / unreachable 放行）
- API：GET /providers/comfyui/workflows + POST .../workflows/{id}/validate
- Agent R0 工具：check_workflow / inspect_comfy（风险分类 + ToolExecutor）
- ComfyMCPIntrospector：动态工具匹配 / 能力缺失回落（fake mcp session，不起真进程）
"""

import asyncio
import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import ProviderUnavailableError, ValidationError
from app.providers.comfyui import client as client_module
from app.providers.comfyui.client import ComfyUIClient
from app.providers.comfyui.introspection import (
    ComfyUIIntrospector,
    parse_enum_choices,
    project_choices,
)
from app.services import workflow_diagnostics_service as diag_module
from app.services.workflow_diagnostics_service import (
    WorkflowDiagnosticsService,
    reset_workflow_diagnostics,
)

BASE = "http://comfy.test:8188"

# 与仓库 workflows/ 目录无关的最小模板（测试通过 settings.workflows_dir 注入）。
# 必须满足 WorkflowSchema 契约：$PROMPT / $SEED / $WIDTH / $HEIGHT 全部出现。
OK_TEMPLATE = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "a.safetensors"},
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "$PROMPT", "clip": ["1", 1]},
    },
    "3": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": "$WIDTH", "height": "$HEIGHT", "batch_size": 1},
    },
    "4": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0],
            "positive": ["2", 0],
            "negative": ["2", 0],
            "latent_image": ["3", 0],
            "sampler_name": "euler",
            "seed": "$SEED",
        },
    },
    "5": {
        "class_type": "SaveImage",
        "inputs": {"images": ["4", 0], "filename_prefix": "studio/shot"},
    },
}

FAKE_OBJECT_INFO = {
    "CheckpointLoaderSimple": {
        "input": {"required": {"ckpt_name": [["a.safetensors", "b.safetensors"], {}]}}
    },
    "CLIPTextEncode": {"input": {"required": {"text": "STRING", "clip": "CLIP"}}},
    "EmptyLatentImage": {"input": {"required": {"width": ["INT", {"min": 0}], "height": ["INT", {"min": 0}]}}},
    "KSampler": {
        "input": {
            "required": {
                "sampler_name": ["euler", "heun", "dpm_2"],
                "seed": ["INT", {"min": 0}],
            }
        }
    },
    "SaveImage": {"input": {"required": {"filename_prefix": "STRING"}}},
}


@pytest.fixture()
def workflows_dir(tmp_path, monkeypatch):
    """把诊断目标模板放进隔离的 workflows 目录（不动真实仓库 workflows/）。"""
    from app.core.config import settings

    (tmp_path / "diag_ok.json").write_text(json.dumps(OK_TEMPLATE), encoding="utf-8")
    original = settings.workflows_dir
    settings.workflows_dir = tmp_path
    yield tmp_path
    settings.workflows_dir = original


@pytest.fixture(autouse=True)
def _reset_diagnostics_singleton():
    reset_workflow_diagnostics()
    yield
    reset_workflow_diagnostics()


class _StubIntrospector:
    """WorkflowIntrospector 测试桩：直接返回预置 choices / 错误。"""

    name = "stub"

    def __init__(self, choices=None, reachable=True, error=None, raise_exc=None):
        self._choices = choices or {}
        self._reachable = reachable
        self._error = error
        self._raise = raise_exc
        self.calls: list[list[str]] = []

    async def resolve_choices(self, class_types):
        self.calls.append(list(class_types))
        if self._raise is not None:
            raise self._raise
        from app.providers.workflow.introspection import EnvironmentSnapshot

        return EnvironmentSnapshot(
            reachable=self._reachable,
            source=self.name,
            choices=self._choices,
            node_count=len(self._choices),
            error=self._error,
        )


# --- ComfyUIClient.get_object_info（async + sync twin） ------------------------


@pytest.fixture()
def comfy(monkeypatch) -> Callable:
    """client_module.httpx 双 shim（AsyncClient + Client）→ MockTransport。"""

    def _build(handler: Callable, base_url: str = BASE) -> ComfyUIClient:
        transport = httpx.MockTransport(handler)

        def _async_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return httpx.AsyncClient(*args, **kwargs)

        def _sync_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return httpx.Client(*args, **kwargs)

        shim = SimpleNamespace(
            AsyncClient=_async_factory,
            Client=_sync_factory,
            HTTPStatusError=httpx.HTTPStatusError,
            TransportError=httpx.TransportError,
        )
        monkeypatch.setattr(client_module, "httpx", shim)
        return ComfyUIClient(base_url=base_url)

    return _build


def test_get_object_info_ok(comfy) -> None:
    client = comfy(lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    info = asyncio.run(client.get_object_info())
    assert info is not None and "KSampler" in info


def test_get_object_info_non_200_is_none(comfy) -> None:
    client = comfy(lambda request: httpx.Response(500))
    assert asyncio.run(client.get_object_info()) is None


def test_get_object_info_transport_error_is_none(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert asyncio.run(comfy(handler).get_object_info()) is None


def test_get_object_info_sync_ok(comfy) -> None:
    client = comfy(lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    info = client.get_object_info_sync()
    assert info is not None and "SaveImage" in info


def test_get_object_info_sync_transport_error_is_none(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert comfy(handler).get_object_info_sync() is None


# --- 枚举解析 / 投影 ------------------------------------------------------------


def test_parse_enum_choices_two_element_form() -> None:
    assert parse_enum_choices([["a.safetensors", "b.safetensors"], {"placeholder": False}]) == [
        "a.safetensors",
        "b.safetensors",
    ]


def test_parse_enum_choices_flat_form() -> None:
    assert parse_enum_choices(["euler", "heun"]) == ["euler", "heun"]


def test_parse_enum_choices_rejects_type_tokens() -> None:
    assert parse_enum_choices(["INT", {"min": 0}]) is None
    assert parse_enum_choices(["STRING"]) is None
    assert parse_enum_choices([42, 0]) is None
    assert parse_enum_choices([]) is None


def test_project_choices_projects_only_requested() -> None:
    choices = project_choices(FAKE_OBJECT_INFO, ["CheckpointLoaderSimple", "KSampler", "MissingNode"])
    assert set(choices) == {"CheckpointLoaderSimple", "KSampler"}
    assert choices["CheckpointLoaderSimple"]["ckpt_name"] == ["a.safetensors", "b.safetensors"]
    # seed 是 ["INT", {...}] 形态 → 不进枚举
    assert "seed" not in choices["KSampler"]


# --- WorkflowDiagnosticsService（sync 原生通道） ---------------------------------


def _sync_service(comfy_fixture, handler) -> WorkflowDiagnosticsService:
    """sync 服务 + 指向 MockTransport 的预填缓存（TTL 内不重发请求）。"""
    import time

    service = WorkflowDiagnosticsService()
    client = comfy_fixture(handler)
    service._sync_cache[client.base_url] = (time.monotonic(), client.get_object_info_sync())
    return service


# sync 服务统一钉到 MockTransport 的 base_url（不依赖开发机真实 ComfyUI 的可达性）。
SYNC_BASE = BASE


def test_sync_diagnostics_ok(comfy, workflows_dir) -> None:
    service = _sync_service(comfy, lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    result = service.validate_workflow_sync("diag_ok", base_url=SYNC_BASE)
    assert result.status == "ok"
    assert result.ok is True
    assert all(n.status == "ok" for n in result.nodes)


def test_sync_diagnostics_missing_node(comfy, workflows_dir) -> None:
    info = {k: v for k, v in FAKE_OBJECT_INFO.items() if k != "KSampler"}
    service = _sync_service(comfy, lambda request: httpx.Response(200, json=info))
    result = service.validate_workflow_sync("diag_ok", base_url=SYNC_BASE)
    assert result.status == "invalid"
    assert result.missing_nodes == ["KSampler"]
    node = next(n for n in result.nodes if n.class_type == "KSampler")
    assert node.status == "missing_node"


def test_sync_diagnostics_missing_model(comfy, workflows_dir) -> None:
    service = _sync_service(comfy, lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    broken = json.loads(json.dumps(OK_TEMPLATE))
    broken["1"]["inputs"]["ckpt_name"] = "gone.safetensors"
    (workflows_dir / "diag_broken_model.json").write_text(json.dumps(broken), encoding="utf-8")
    result = service.validate_workflow_sync("diag_broken_model", base_url=SYNC_BASE)
    assert result.status == "invalid"
    assert result.missing_models == ["gone.safetensors (CheckpointLoaderSimple.ckpt_name)"]


def test_sync_diagnostics_broken_link(comfy, workflows_dir) -> None:
    service = _sync_service(comfy, lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    broken = json.loads(json.dumps(OK_TEMPLATE))
    broken["5"]["inputs"]["images"] = ["999", 0]
    (workflows_dir / "diag_broken_link.json").write_text(json.dumps(broken), encoding="utf-8")
    result = service.validate_workflow_sync("diag_broken_link", base_url=SYNC_BASE)
    assert result.status == "invalid"
    assert result.broken_links == ["5.images -> '999'"]


def test_sync_diagnostics_unreachable(comfy, workflows_dir) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    import time

    service = WorkflowDiagnosticsService()
    client = comfy(handler)
    # 预填 None（模拟探测失败的 TTL 缓存），避免依赖开发机真实 ComfyUI 可达性。
    service._sync_cache[client.base_url] = (time.monotonic(), None)
    result = service.validate_workflow_sync("diag_ok", base_url=SYNC_BASE)
    assert result.status == "unreachable"
    assert result.ok is False


def test_sync_diagnostics_static_error(comfy, workflows_dir) -> None:
    (workflows_dir / "diag_bad.json").write_text(json.dumps({"1": {"class_type": "KSampler"}}), encoding="utf-8")
    service = _sync_service(comfy, lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    result = service.validate_workflow_sync("diag_bad", base_url=SYNC_BASE)
    assert result.status == "static_error"
    assert result.static_error is not None


def test_sync_diagnostics_unknown_workflow_id_raises(workflows_dir) -> None:
    service = WorkflowDiagnosticsService()
    with pytest.raises(ValidationError):
        service.validate_workflow_sync("no_such_workflow")


# --- async 通道（introspector 选择 / MCP 回落） ----------------------------------


def test_async_uses_injected_introspector(workflows_dir) -> None:
    choices = {
        "CheckpointLoaderSimple": {"ckpt_name": ["a.safetensors"]},
        "CLIPTextEncode": {},
        "EmptyLatentImage": {},
        "KSampler": {},
        "SaveImage": {},
    }
    stub = _StubIntrospector(choices=choices)
    result = asyncio.run(WorkflowDiagnosticsService(introspector=stub).validate_workflow_async("diag_ok"))
    assert result.status == "ok"
    assert result.source == "stub"
    assert set(stub.calls[0]) == set(choices)


def test_async_unreachable_from_introspector(workflows_dir) -> None:
    stub = _StubIntrospector(reachable=False, error="down")
    result = asyncio.run(WorkflowDiagnosticsService(introspector=stub).validate_workflow_async("diag_ok"))
    assert result.status == "unreachable"
    assert result.error == "down"


def test_async_introspector_crash_returns_unreachable(workflows_dir) -> None:
    stub = _StubIntrospector(raise_exc=RuntimeError("boom"))
    result = asyncio.run(WorkflowDiagnosticsService(introspector=stub).validate_workflow_async("diag_ok"))
    # 非 ProviderUnavailableError 的崩溃也降级为 unreachable（诊断永不 500）
    assert result.status == "unreachable"
    assert "boom" in (result.error or "")


def test_native_async_roundtrip(comfy, workflows_dir) -> None:
    introspector = ComfyUIIntrospector(base_url=BASE)
    # 注入 MockTransport（comfy fixture shim 作用于 client_module）
    comfy(lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    service = WorkflowDiagnosticsService(introspector=introspector)
    result = asyncio.run(service.validate_workflow_async("diag_ok"))
    assert result.status == "ok"
    assert result.source == "native"


# --- create_generation fail-fast（live guard） ----------------------------------


def _service_with_invalid_diagnostics(monkeypatch) -> None:
    class _InvalidStub(WorkflowDiagnosticsService):
        def validate_workflow_sync(self, workflow_id=None, base_url=None):
            from app.providers.workflow.introspection import WorkflowDiagnostics

            return WorkflowDiagnostics(
                workflow_id=workflow_id or "default_image_api",
                status="invalid",
                missing_nodes=["WanVideoSampler"],
                missing_models=["missing.safetensors (UNETLoader.unet_name)"],
            )

    monkeypatch.setattr(diag_module, "_diagnostics_service", _InvalidStub())


def test_live_workflow_guard_blocks_invalid(monkeypatch, comfy) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "image_provider", "comfyui")
    _service_with_invalid_diagnostics(monkeypatch)
    from app.services.generation_service import GenerationService

    service = GenerationService.__new__(GenerationService)  # 只测 guard，无需 DB
    with pytest.raises(ValidationError) as excinfo:
        service._live_workflow_guard("default_image_api", "comfyui")
    assert excinfo.value.details["missing_nodes"] == ["WanVideoSampler"]


def test_live_workflow_guard_allows_unreachable(monkeypatch, comfy) -> None:
    class _UnreachableStub(WorkflowDiagnosticsService):
        def validate_workflow_sync(self, workflow_id=None, base_url=None):
            from app.providers.workflow.introspection import WorkflowDiagnostics

            return WorkflowDiagnostics(workflow_id="x", status="unreachable", error="down")

    monkeypatch.setattr(diag_module, "_diagnostics_service", _UnreachableStub())
    from app.services.generation_service import GenerationService

    service = GenerationService.__new__(GenerationService)
    service._live_workflow_guard("default_image_api", "comfyui")  # 不抛


def test_live_workflow_guard_ignores_non_comfyui() -> None:
    from app.services.generation_service import GenerationService

    service = GenerationService.__new__(GenerationService)
    service._live_workflow_guard("default_image_api", "mock")  # 不抛、不探测


# --- API 端点 -------------------------------------------------------------------


def test_api_list_workflows(client) -> None:
    resp = client.get("/api/v1/providers/comfyui/workflows")
    assert resp.status_code == 200
    ids = [w["id"] for w in resp.json()["workflows"]]
    assert "default_image_api" in ids
    default = next(w for w in resp.json()["workflows"] if w["id"] == "default_image_api")
    assert default["is_default"] is True


def test_api_validate_ok_and_invalid(client, monkeypatch) -> None:
    # default_image_api 模板涉及的全部 class_types
    ok_choices = {
        "CheckpointLoaderSimple": {"ckpt_name": ["v1.safetensors", "v2.safetensors"]},
        "CLIPTextEncode": {},
        "EmptyLatentImage": {},
        "KSampler": {},
        "VAEDecode": {},
        "SaveImage": {},
    }

    class _OkStub(_StubIntrospector):
        def __init__(self):
            super().__init__(choices=ok_choices)

    monkeypatch.setattr(diag_module, "_diagnostics_service", WorkflowDiagnosticsService(introspector=_OkStub()))
    resp = client.post("/api/v1/providers/comfyui/workflows/default_image_api/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok" and body["ok"] is True

    class _InvalidStub(_StubIntrospector):
        def __init__(self):
            super().__init__(choices={k: {} for k in ok_choices if k != "CheckpointLoaderSimple"})

    monkeypatch.setattr(diag_module, "_diagnostics_service", WorkflowDiagnosticsService(introspector=_InvalidStub()))
    resp = client.post("/api/v1/providers/comfyui/workflows/default_image_api/validate")
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "invalid"
    assert body["missing_nodes"] == ["CheckpointLoaderSimple"]


def test_api_validate_unknown_workflow_422(client) -> None:
    resp = client.post("/api/v1/providers/comfyui/workflows/no_such_id/validate")
    assert resp.status_code == 422


def test_api_validate_unreachable_is_200(client, monkeypatch) -> None:
    stub = _StubIntrospector(reachable=False, error="down")
    monkeypatch.setattr(diag_module, "_diagnostics_service", WorkflowDiagnosticsService(introspector=stub))
    resp = client.post("/api/v1/providers/comfyui/workflows/default_image_api/validate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"


def test_api_validate_crash_never_500(client, monkeypatch) -> None:
    stub = _StubIntrospector(raise_exc=RuntimeError("boom"))
    monkeypatch.setattr(diag_module, "_diagnostics_service", WorkflowDiagnosticsService(introspector=stub))
    resp = client.post("/api/v1/providers/comfyui/workflows/default_image_api/validate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"


# --- Agent R0 工具 ---------------------------------------------------------------


def test_risk_classification_check_tools_are_r0() -> None:
    from app.agents.risk import classify_tool_operation, requires_approval

    for tool in ("check_workflow", "inspect_comfy"):
        assessment = classify_tool_operation(tool, {})
        assert assessment.risk_level == "R0"
        assert requires_approval(assessment) is False


def test_tool_executor_check_workflow(monkeypatch, workflows_dir) -> None:
    from app.agents.tools import ToolExecutor

    # ToolExecutor 走 sync 通道；stub introspector 只影响 async —— 这里直接给
    # singleton 换成返回 ok 的 sync 桩。
    class _SyncOk(WorkflowDiagnosticsService):
        def validate_workflow_sync(self, workflow_id=None, base_url=None):
            from app.providers.workflow.introspection import WorkflowDiagnostics

            return WorkflowDiagnostics(workflow_id=workflow_id or "diag_ok", status="ok", source="native")

    monkeypatch.setattr(diag_module, "_diagnostics_service", _SyncOk())
    executor = ToolExecutor(None)  # 检查通道工具不触 DB
    result = executor.execute(
        SimpleNamespace(tool="check_workflow", arguments={"workflow_id": "diag_ok"})
    )
    assert result.success is True
    assert result.data["status"] == "ok"
    assert "完全兼容" in result.data["summary"]


def test_tool_executor_check_workflow_invalid_summary(client, monkeypatch) -> None:
    from app.agents.tools import ToolExecutor

    class _SyncInvalid(WorkflowDiagnosticsService):
        def validate_workflow_sync(self, workflow_id=None, base_url=None):
            from app.providers.workflow.introspection import WorkflowDiagnostics

            return WorkflowDiagnostics(
                workflow_id="x",
                status="invalid",
                missing_nodes=["WanVideoSampler"],
                missing_models=["m.safetensors (UNETLoader.unet_name)"],
            )

    monkeypatch.setattr(diag_module, "_diagnostics_service", _SyncInvalid())
    executor = ToolExecutor(None)
    result = executor.execute(SimpleNamespace(tool="check_workflow", arguments={}))
    assert result.success is True
    assert "缺节点 WanVideoSampler" in result.data["summary"]
    assert "缺模型" in result.data["summary"]


def test_tool_executor_inspect_comfy(comfy, monkeypatch) -> None:
    from app.agents.tools import ToolExecutor
    from app.core.config import settings

    comfy(lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))
    executor = ToolExecutor(None)
    result = executor.execute(SimpleNamespace(tool="inspect_comfy", arguments={}))
    assert result.success is True
    assert result.data["reachable"] is True
    assert result.data["node_count"] == len(FAKE_OBJECT_INFO)
    assert "default_image_api" in result.data["workflows"]
    assert result.data["introspection_mode"] == settings.comfy_introspection


def test_tool_executor_inspect_comfy_down(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    comfy(handler)
    from app.agents.tools import ToolExecutor

    executor = ToolExecutor(None)
    result = executor.execute(SimpleNamespace(tool="inspect_comfy", arguments={}))
    assert result.success is True
    assert result.data["reachable"] is False


# --- ComfyMCPIntrospector（fake mcp session，不起真进程） -------------------------


class _FakeTool:
    def __init__(self, name: str, input_schema: dict | None = None):
        self.name = name
        self.inputSchema = input_schema or {"properties": {"query": {"type": "string"}}}


class _FakeSession:
    def __init__(self, tools: list[_FakeTool], responses: dict[str, object]):
        self._tools = tools
        self._responses = responses
        self.initialized = False
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self):
        self.initialized = True

    async def list_tools(self):
        return SimpleNamespace(tools=self._tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        payload = self._responses[name]
        if isinstance(payload, Exception):
            raise payload
        return SimpleNamespace(
            structuredContent=None,
            content=[SimpleNamespace(text=json.dumps(payload))],
            isError=False,
        )


def _fake_mcp_modules(monkeypatch, session: _FakeSession) -> None:
    """把 mcp sdk 的三个入口替换为 fake（不启动 comfy-mcp 子进程）。"""

    @asynccontextmanager
    async def fake_stdio_client(params):
        yield (object(), object())

    fake_mcp = SimpleNamespace(ClientSession=lambda read, write: session, StdioServerParameters=lambda **kw: None)
    fake_stdio = SimpleNamespace(stdio_client=fake_stdio_client)

    import sys
    import types

    monkeypatch.setattr("mcp.ClientSession", fake_mcp.ClientSession, raising=False)
    monkeypatch.setattr("mcp.StdioServerParameters", fake_mcp.StdioServerParameters, raising=False)
    monkeypatch.setattr("mcp.client.stdio.stdio_client", fake_stdio.stdio_client, raising=False)
    # 宽松兜底：若测试环境未安装 mcp，注入假模块
    for name, _mod in (("mcp", fake_mcp), ("mcp.client.stdio", fake_stdio)):
        if name not in sys.modules:
            sys.modules[name] = types.SimpleNamespace()


def test_mcp_introspector_matches_node_tool(monkeypatch) -> None:
    from app.providers.comfyui.mcp_introspection import ComfyMCPIntrospector

    session = _FakeSession(
        tools=[_FakeTool("search_nodes"), _FakeTool("run_workflow")],
        responses={"search_nodes": FAKE_OBJECT_INFO["KSampler"]},
    )
    _fake_mcp_modules(monkeypatch, session)
    snapshot = asyncio.run(ComfyMCPIntrospector().resolve_choices(["KSampler"]))
    assert snapshot.reachable is True
    assert snapshot.source == "mcp"
    assert "KSampler" in snapshot.choices
    assert session.calls[0][0] == "search_nodes"


def test_mcp_introspector_missing_node_tool_raises(monkeypatch) -> None:
    from app.providers.comfyui.mcp_introspection import ComfyMCPIntrospector

    session = _FakeSession(
        tools=[_FakeTool("run_workflow"), _FakeTool("search_models")],
        responses={},
    )
    _fake_mcp_modules(monkeypatch, session)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(ComfyMCPIntrospector().resolve_choices(["KSampler"]))


def test_mcp_introspector_connection_failure_raises(monkeypatch) -> None:
    from app.providers.comfyui.mcp_introspection import ComfyMCPIntrospector

    @asynccontextmanager
    async def failing_stdio(params):
        raise RuntimeError("comfy not found")
        yield  # pragma: no cover

    import mcp.client.stdio as stdio_mod

    monkeypatch.setattr(stdio_mod, "stdio_client", failing_stdio, raising=False)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(ComfyMCPIntrospector().resolve_choices(["KSampler"]))


def test_service_falls_back_to_native_when_mcp_unavailable(comfy, monkeypatch, workflows_dir) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "comfy_introspection", "mcp")
    comfy(lambda request: httpx.Response(200, json=FAKE_OBJECT_INFO))

    @asynccontextmanager
    async def failing_stdio(params):
        raise RuntimeError("comfy-mcp not installed")
        yield  # pragma: no cover

    import mcp.client.stdio as stdio_mod

    monkeypatch.setattr(stdio_mod, "stdio_client", failing_stdio, raising=False)
    service = WorkflowDiagnosticsService()
    result = asyncio.run(service.validate_workflow_async("diag_ok"))
    assert result.status == "ok"
    assert result.source == "native"  # MCP 连接失败 → ProviderUnavailableError → 回落
