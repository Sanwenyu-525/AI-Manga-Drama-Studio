"""Application configuration (pydantic-settings, env prefix STUDIO_)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STUDIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Manga Drama Studio"
    app_env: str = "development"  # development | test | production
    api_prefix: str = "/api/v1"

    host: str = "127.0.0.1"
    port: int = 17820

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

    # LLM (Stage B): "fake" = deterministic FakeLLMGateway (no key needed, default for dev/tests);
    # "openai" = OpenAI-compatible endpoint via LangChain ChatOpenAI (DeepSeek / Ollama / vLLM / OpenAI).
    llm_mode: str = "fake"  # fake | openai
    llm_base_url: str | None = None
    llm_api_key: str | None = None  # prefer env STUDIO_LLM_API_KEY; never stored in DB
    llm_model: str = "deepseek-chat"
    llm_structured_method: str = "json_schema"  # json_schema | function_calling

    # Generation (Stage C): "mock" = MockImageProvider (deterministic test image, default);
    # "comfyui" = external ComfyUI server (user-started, mvp-spec §8).
    image_provider: str = "mock"  # mock | comfyui
    comfyui_url: str = "http://127.0.0.1:8188"
    generation_concurrency: int = 1  # ComfyUI queue is serial; keep 1 for MVP
    generation_max_attempts: int = 3

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


settings = Settings()
