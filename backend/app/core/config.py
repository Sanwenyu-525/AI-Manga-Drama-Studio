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
        "tauri://localhost",
        "http://tauri.localhost",
    ]

    # Logging
    log_level: str = "INFO"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


settings = Settings()
