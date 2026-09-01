"""ProviderRegistry (backend-architecture §17, §37; mvp-spec §65; P4-T002).

Generalizes the previous single-type (image) registry into a multi-type registry:
each media/LLM producer type has its own providerId -> adapter map, all resolvable
by canonical id. Unknown ids ALWAYS raise ValidationError (422) — never a silent
fallback. The existing get_image_provider() signature is preserved so current
callers (GenerationService / worker) are untouched.

Types / canonical provider ids:
  image    : mock | comfyui | agnes  (existing, unchanged)
  video    : mock                     (MVP placeholder -> "unavailable", fails fast)
  workflow : comfyui                  (WorkflowProviderAdapter over WorkflowMapper)
  llm      : fake | openai            (LlmProviderAdapter = LLMGateway, via factory)
  audio    : mock | edge              (TASK-012 voiceover synthesis)

provider_status() now emits every registered provider with complete capabilities
(image_generation / reference_image / video_generation / text_generation), merged
with the ProviderHealthService health block in api/providers.py (backward compatible).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.providers.audio import AudioProvider, EdgeTTSAudioProvider, MockAudioProvider
from app.providers.image.base import ImageProvider
from app.providers.image.agnes import AgnesImageProvider
from app.providers.image.comfyui import ComfyUIProvider
from app.providers.image.mock import MockImageProvider
from app.providers.render.base import RenderProviderProtocol
from app.providers.render.ffmpeg import FFmpegRenderProvider
from app.providers.render.mock import MockRenderProvider
from app.providers.llm import LlmProviderAdapter, create_gateway, reset_gateway
from app.providers.video import VideoProviderProtocol, VideoProviderUnavailable
from app.providers.video.agnes import AgnesVideoProvider
from app.providers.workflow import ComfyUIWorkflowProviderAdapter, WorkflowProviderAdapter

logger = get_logger("providers.registry")

# Canonical provider-id sets per type.
IMAGE_PROVIDERS = ("mock", "comfyui", "agnes")
VIDEO_PROVIDERS = ("mock", "agnes")
RENDER_PROVIDERS = ("auto", "mock", "ffmpeg")
WORKFLOW_PROVIDERS = ("comfyui",)
LLM_PROVIDERS = ("fake", "openai")
AUDIO_PROVIDERS = ("mock", "edge")

# --- image ---
_image_providers: dict[str, ImageProvider] = {}
_comfyui_provider: ComfyUIProvider | None = None

# --- video (mock placeholder + agnes 真实云视频) ---
_video_providers: dict[str, VideoProviderProtocol] = {}

# --- render (Phase 9 P9-E3: timeline episode render) ---
_render_providers: dict[str, RenderProviderProtocol] = {}

# --- workflow ---
_workflow_providers: dict[str, WorkflowProviderAdapter] = {}

# --- llm ---
_llm_providers: dict[str, LlmProviderAdapter] = {}

# --- audio (TASK-012 voiceover) ---
_audio_providers: dict[str, AudioProvider] = {}


# ------------------------------ image ------------------------------
def get_image_provider(provider_id: str | None = None) -> ImageProvider:
    """Resolve a canonical image provider id -> the implementation that will actually run.

    provider_id=None -> studio default（运行时 image.json 的 provider，env 兜底，
    与设置页「图像服务」同源）。Unknown ids raise ValidationError (422).
    Signature preserved for existing callers.
    """
    from app.services.image_settings_service import get_image_config

    pid = provider_id or get_image_config()["provider"]
    if pid not in IMAGE_PROVIDERS:
        raise ValidationError(
            "Unknown image provider.",
            {"provider": pid, "supported": list(IMAGE_PROVIDERS)},
        )
    cached = _image_providers.get(pid)
    if cached is not None:
        return cached
    if pid == "comfyui":
        provider: ImageProvider = get_comfyui_provider()
        logger.info("image provider: comfyui (%s)", settings.comfyui_url)
    elif pid == "agnes":
        provider = AgnesImageProvider()
        logger.info("image provider: agnes (runtime image config)")
    else:
        provider = MockImageProvider()
        logger.info("image provider: mock (default; set comfyui/agnes for real generation)")
    _image_providers[pid] = provider
    return provider


def get_comfyui_provider() -> ComfyUIProvider:
    global _comfyui_provider
    if _comfyui_provider is None:
        _comfyui_provider = ComfyUIProvider()
    return _comfyui_provider


# ------------------------------ video ------------------------------
def get_video_provider(provider_id: str | None = None) -> VideoProviderProtocol:
    """Resolve a canonical video provider id.

    provider_id=None -> studio default（运行时 image.json 的 video_provider，env 兜底，
    与设置页「视频服务」同源）。Unknown ids raise ValidationError (422).
    """
    from app.services.image_settings_service import get_video_config

    pid = provider_id or get_video_config()["provider"]
    if pid not in VIDEO_PROVIDERS:
        raise ValidationError(
            "Unknown video provider.",
            {"provider": pid, "supported": list(VIDEO_PROVIDERS)},
        )
    cached = _video_providers.get(pid)
    if cached is not None:
        return cached
    if pid == "agnes":
        provider: VideoProviderProtocol = AgnesVideoProvider()
        logger.info("video provider: agnes (runtime video config)")
    else:
        provider = VideoProviderUnavailable()
        logger.info("video provider: mock (placeholder — unavailable; select agnes for real video)")
    _video_providers[pid] = provider
    return provider

# ------------------------------ render (Phase 9) ----------------------------
def resolve_render_provider_id(provider_id: str | None = None) -> str:
    """Resolve the effective render provider id (auto → ffmpeg if available else mock)."""
    pid = provider_id or settings.render_provider
    if pid == "auto":
        from app.providers.render.ffmpeg import _ffmpeg_binary

        return "ffmpeg" if _ffmpeg_binary() is not None else "mock"
    return pid


def get_render_provider(provider_id: str | None = None) -> RenderProviderProtocol:
    """Resolve the render provider that actually assembles timeline videos.

    provider_id=None → settings.render_provider ("auto" probes for ffmpeg).
    Unknown ids always raise ValidationError (422); explicit "ffmpeg" without a
    local binary fails fast in the provider itself (never a silent fallback).
    """
    pid = resolve_render_provider_id(provider_id)
    if pid not in RENDER_PROVIDERS:
        raise ValidationError(
            "Unknown render provider.",
            {"provider": pid, "supported": list(RENDER_PROVIDERS)},
        )
    cached = _render_providers.get(pid)
    if cached is not None:
        return cached
    if pid == "ffmpeg":
        provider: RenderProviderProtocol = FFmpegRenderProvider()
        logger.info("render provider: ffmpeg (local H.264 encode)")
    else:
        provider = MockRenderProvider()
        logger.info("render provider: mock (pure-Python MJPEG AVI — dev/test default)")
    _render_providers[pid] = provider
    return provider


# ----------------------------- workflow ----------------------------
def get_workflow_provider(provider_id: str | None = None) -> WorkflowProviderAdapter:
    """Resolve the workflow adapter (builds ComfyUI workflows for a canonical id).

    Business code builds workflows only through this adapter — never by touching the
    template dir directly (P4-T001). Unknown id -> ValidationError (422).
    """
    pid = provider_id or "comfyui"
    if pid not in WORKFLOW_PROVIDERS:
        raise ValidationError(
            "Unknown workflow provider.",
            {"provider": pid, "supported": list(WORKFLOW_PROVIDERS)},
        )
    cached = _workflow_providers.get(pid)
    if cached is not None:
        return cached
    provider: WorkflowProviderAdapter = ComfyUIWorkflowProviderAdapter()
    logger.info("workflow provider: %s (WorkflowMapper adapter)", pid)
    _workflow_providers[pid] = provider
    return provider


# ------------------------------- llm -------------------------------
def get_llm_provider(provider_id: str | None = None) -> LlmProviderAdapter:
    """Resolve an LLM adapter id -> a concrete LLMGateway (via app.llm.factory).

    provider_id=None -> 激活连接的 mode（与 create_gateway 默认任务同源）。
    Unknown id -> ValidationError (422).
    """
    if provider_id:
        pid = provider_id
    else:
        from app.services.llm_settings_service import get_llm_config

        pid = get_llm_config()["mode"]
    if pid not in LLM_PROVIDERS:
        raise ValidationError(
            "Unknown llm provider.",
            {"provider": pid, "supported": list(LLM_PROVIDERS)},
        )
    if pid not in _llm_providers:
        # Explicit "fake" must always resolve deterministically (tests/CI never hit
        # the network); only the openai path (or default) reads the saved runtime
        # config via the factory.
        if pid == "fake":
            from app.llm.fake import FakeLLMGateway

            _llm_providers[pid] = FakeLLMGateway()
        else:
            _llm_providers[pid] = create_gateway()
    return _llm_providers[pid]


# ------------------------------ audio ------------------------------
def get_audio_provider(provider_id: str | None = None) -> AudioProvider:
    """Resolve a canonical audio provider id -> the implementation that will run.

    provider_id=None -> studio default (settings.audio_provider). Unknown ids
    raise ValidationError (422) — same fail-fast rule as the other types.
    """
    pid = provider_id or settings.audio_provider
    if pid not in AUDIO_PROVIDERS:
        raise ValidationError(
            "Unknown audio provider.",
            {"provider": pid, "supported": list(AUDIO_PROVIDERS)},
        )
    cached = _audio_providers.get(pid)
    if cached is not None:
        return cached
    if pid == "edge":
        provider: AudioProvider = EdgeTTSAudioProvider()
        logger.info("audio provider: edge (STUDIO_AUDIO_PROVIDER=edge; needs the edge-tts package)")
    else:
        provider = MockAudioProvider()
        logger.info("audio provider: mock (deterministic WAV — dev/test default)")
    _audio_providers[pid] = provider
    return provider


# --------------------------- capabilities --------------------------
# Complete capability map per canonical (type, provider_id) — contract §47 / §130-131.
_CAPABILITIES: dict[str, dict[str, bool]] = {
    "image.mock": {"image_generation": True, "reference_image": False},
    "image.comfyui": {"image_generation": True, "reference_image": True},
    "image.agnes": {"image_generation": True, "reference_image": False},
    "video.mock": {"video_generation": False},  # registered but unavailable (MVP)
    "video.agnes": {"video_generation": True},
    "workflow.comfyui": {"workflow": True},
    "render.mock": {"video_render": True},
    "render.ffmpeg": {"video_render": True},
    "llm.fake": {"text_generation": True},
    "llm.openai": {"text_generation": True},
    "audio.mock": {"audio_generation": True},
    "audio.edge": {"audio_generation": True},
}


def image_provider_supports_reference(provider_id: str | None) -> bool:
    """Capability probe: does this canonical image provider accept reference images?

    Mechanical lookup for the worker's row→request conversion (generations/worker.py);
    no business semantics here (red line: providers/worker never know character/shot logic).
    Unknown ids → False (honest degradation, same table as provider_status()).
    """
    return bool(_CAPABILITIES.get(f"image.{provider_id}", {}).get("reference_image", False))


def provider_status() -> list[dict]:
    """Provider status DTO for every registered type (contract §47).

    Backward compatible: image entries keep their legacy id/name/type/status/
    capabilities/base_url fields; new video/workflow/llm entries are additive.
    """
    # LLM 激活态与业务链路（create_gateway → get_llm_config）同源：
    # 运行时保存配置（llm_profiles.json/llm.json）优先，env 兜底 —— 而非静态
    # settings.llm_mode，否则设置页切换后状态栏仍显示旧 Provider（误导用户）。
    from app.services.image_settings_service import get_image_config, get_video_config
    from app.services.llm_settings_service import get_config_read

    llm_read = get_config_read()
    llm_mode = llm_read["mode"]
    image_cfg = get_image_config()
    video_cfg = get_video_config()
    providers: list[dict] = [
        {
            "id": "mock",
            "name": "Mock Image Provider",
            "type": "image",
            "status": "connected",
            "capabilities": dict(_CAPABILITIES["image.mock"]),
        },
        {
            "id": "comfyui_local",
            "name": "Local ComfyUI",
            "type": "image",
            "status": "unknown",
            "capabilities": dict(_CAPABILITIES["image.comfyui"]),
            "base_url": settings.comfyui_url,
        },
        {
            "id": "agnes",
            "name": "Agnes Cloud Image",
            "type": "image",
            "status": "active" if image_cfg["provider"] == "agnes" else "unknown",
            "capabilities": dict(_CAPABILITIES["image.agnes"]),
            "base_url": image_cfg["agnes_base_url"],
        },
        # Video: mock placeholder stays "unavailable"; agnes reflects runtime config.
        {
            "id": "video_mock",
            "name": "Mock Video Provider (unavailable)",
            "type": "video",
            "status": "unavailable",
            "capabilities": dict(_CAPABILITIES["video.mock"]),
        },
        {
            "id": "video_agnes",
            "name": "Agnes Cloud Video",
            "type": "video",
            "status": "active" if video_cfg["provider"] == "agnes" else "unknown",
            "capabilities": {"video_generation": True},
        },
        {
            "id": "workflow_comfyui",
            "name": "ComfyUI Workflow Adapter",
            "type": "workflow",
            "status": "connected",
            "capabilities": dict(_CAPABILITIES["workflow.comfyui"]),
        },
        {
            "id": "llm_fake",
            "name": "Fake LLM Gateway",
            "type": "llm",
            "status": "active" if llm_mode == "fake" else "unknown",
            "capabilities": dict(_CAPABILITIES["llm.fake"]),
        },
        {
            "id": "llm_openai",
            "name": "OpenAI-compatible LLM Gateway",
            "type": "llm",
            "status": "active" if llm_mode == "openai" else "unknown",
            "capabilities": dict(_CAPABILITIES["llm.openai"]),
            "base_url": settings.llm_base_url,
            # 激活连接的 per-model 能力标记（advisory，供 UI/运行时参考）
            "model_capabilities": llm_read.get("capabilities"),
            "model": llm_read.get("model"),
        },
        {
            "id": "audio_mock",
            "name": "Mock Audio Provider",
            "type": "audio",
            "status": "connected",
            "capabilities": dict(_CAPABILITIES["audio.mock"]),
        },
        {
            "id": "audio_edge",
            "name": "Edge Neural TTS (online)",
            "type": "audio",
            "status": "active" if settings.audio_provider == "edge" else "unknown",
            "capabilities": dict(_CAPABILITIES["audio.edge"]),
        },
    ]
    if image_cfg["provider"] == "comfyui":
        providers[1]["status"] = "active"
    return providers


def reset_image_providers() -> None:
    """Reset cached image providers（图像运行时配置变更后调用）.

    必须同时清 ComfyUI Provider 单例：它持有按运行时 image.json 解析的
    comfyui_url / checkpoint，配置变更后旧实例作废。
    """
    global _comfyui_provider
    _image_providers.clear()
    _comfyui_provider = None


def reset_video_providers() -> None:
    """Reset only the cached video providers（视频运行时配置变更后调用）."""
    _video_providers.clear()


def reset_providers() -> None:
    """Reset cached providers (used by tests)."""
    global _comfyui_provider
    _image_providers.clear()
    _video_providers.clear()
    _video_providers.clear()
    _render_providers.clear()
    _workflow_providers.clear()
    _llm_providers.clear()
    _audio_providers.clear()
    _comfyui_provider = None
    reset_gateway()
