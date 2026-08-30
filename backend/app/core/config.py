"""Application configuration (pydantic-settings, env prefix STUDIO_)."""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STUDIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Manga Drama Studio"
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"

    host: str = "127.0.0.1"
    port: int = 17820

    # Local session token (P1-E5-T02): set by the Tauri shell when it spawns the
    # backend. When set, every REST request must carry X-Session-Token and the WS
    # connection must pass ?token= (except /health + /system/info handshake).
    # None = development/dev-shell backend → auth is off (local API open), which
    # keeps the browser dev flow convenient. Never logged, never stored in the DB.
    session_token: str | None = None

    # Data directory: SQLite file + project assets live here (relative paths only in DB).
    data_dir: Path = BACKEND_DIR / "data"

    # CORS: Vite dev server + Tauri webview.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:17821",
        "http://127.0.0.1:17821",
        "tauri://localhost",
        "http://tauri.localhost",
    ]

    # Logging
    log_level: str = "INFO"

    # LLM (Stage B): "fake" = deterministic FakeLLMGateway (dev/test only, no key needed);
    # "openai" = OpenAI-compatible endpoint via LangChain ChatOpenAI (DeepSeek / Ollama / vLLM / OpenAI).
    # fake 仅用于测试与无 key 开发；真实产品链路必须 openai（见 app.llm.factory 降级策略）。
    llm_mode: Literal["fake", "openai"] = "fake"  # fake = dev/test only (P1-E5-T01)
    llm_base_url: str | None = None
    llm_api_key: str | None = None  # prefer env STUDIO_LLM_API_KEY; never stored in DB
    llm_model: str = "deepseek-chat"
    llm_structured_method: str = "json_schema"  # json_schema | function_calling

    # Generation (Stage C): "mock" = MockImageProvider (deterministic test image, default);
    # "comfyui" = external ComfyUI server (user-started, mvp-spec §8).
    # P1-E2-T01: Literal type → invalid provider values fail at startup/preflight.
    image_provider: Literal["mock", "comfyui", "agnes"] = "mock"
    comfyui_url: str = "http://127.0.0.1:8188"
    # Agnes image API (real cloud text-to-image; stage C real generation without a GPU).
    # Key is optional in Settings so startup never fails without it — the provider
    # surfaces a clear error only when an agnes generation is actually requested.
    agnes_api_key: str | None = None  # prefer env STUDIO_AGNES_API_KEY; never stored in DB
    agnes_base_url: str = "https://api.agnes-ai.cn/v1"
    video_provider: Literal["mock", "agnes"] = "mock"  # mock = dev/test only (P1-E5-T01)
    video_model: str = "agnes-video-2.5-flash"
    generation_concurrency: int = 1  # P1-E2-T02: MVP supports exactly ONE worker — see validator
    generation_max_attempts: int = 3
    generation_lease_seconds: int = 120  # P1-E2-T02: claim lease (crash recovery window)
    generation_retry_backoff_base: float = 1.0  # seconds; doubles per attempt
    generation_retry_backoff_max: float = 60.0  # cap for the exponential backoff

    # Render (Phase 9): "auto" picks a local ffmpeg when present, else the
    # pure-Python mock (MJPEG AVI). Explicit "mock"/"ffmpeg" override the probe.
    render_provider: Literal["auto", "mock", "ffmpeg"] = "auto"

    # Voiceover TTS (TASK-012): "mock" = deterministic WAV (dev/test default);
    # "edge" = online neural voices via the edge-tts package (no key/GPU needed,
    # but an undocumented Microsoft endpoint — dev/prototyping, not prod default).
    audio_provider: Literal["mock", "edge"] = "mock"
    tts_default_voice: str = "zh-CN-XiaoxiaoNeural"

    @field_validator("generation_concurrency")
    @classmethod
    def _single_worker_only(cls, value: int) -> int:
        """P1-E2-T02: we do not fake parallelism — concurrency>1 is rejected at startup."""
        if value != 1:
            raise ValueError("MVP supports exactly one generation worker (generation_concurrency=1).")
        return value

    # ComfyUI workflow templates (P1-E2-T01): default = repo root workflows/;
    # override with STUDIO_WORKFLOWS_DIR for packaged/bundled layouts.
    workflows_dir: Path = REPO_ROOT / "workflows"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


settings = Settings()


# P1-E5-T01: production must not silently produce fake results. development/test
# keep the fake/mock defaults (convenient and visible); in production a fake-content
# provider is refused at startup instead of generating plausible-looking fake output.
# Called from the app lifespan (so tests can pin app_env first), not from the Settings
# constructor (which would make the fail-closed case impossible to construct/test).
def validate_startup_config(s: "Settings") -> None:
    """Raise RuntimeError if the production environment would produce fake content."""
    if s.app_env != "production":
        return
    problems: list[str] = []
    if s.llm_mode == "fake":
        problems.append("STUDIO_LLM_MODE=fake — set STUDIO_LLM_MODE=openai with a real base_url/key")
    if s.image_provider == "mock":
        problems.append("STUDIO_IMAGE_PROVIDER=mock — set comfyui or agnes")
    if s.video_provider == "mock":
        problems.append("STUDIO_VIDEO_PROVIDER=mock — set agnes")
    if s.audio_provider == "mock":
        problems.append("STUDIO_AUDIO_PROVIDER=mock — set edge or a real TTS")
    if problems:
        raise RuntimeError(
            "Production startup refused: fake/mock providers would silently produce fake results.\n"
            + "  - " + "\n  - ".join(problems)
        )
