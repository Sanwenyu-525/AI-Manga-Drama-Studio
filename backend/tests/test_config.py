"""P1-E5-T01 — production config fail-closed + dependency/env contract.

- production must not silently boot with fake-content providers (FakeLLM /
  MockImageProvider / mock video / mock audio) — validate_startup_config refuses.
- development/test keep the fake/mock defaults, convenient and visible.
- invalid provider/mode/env values fail at Settings construction (Literal) or
  at save time (422) instead of silently falling back.
- .env.example carries no real secrets; the lock file is reproducible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, validate_startup_config


def _prod(**overrides) -> Settings:
    base = {
        "app_env": "production",
        "llm_mode": "openai",
        "image_provider": "agnes",
        "video_provider": "agnes",
        "audio_provider": "edge",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_production_rejects_fake_llm() -> None:
    s = _prod(llm_mode="fake")
    with pytest.raises(RuntimeError, match="STUDIO_LLM_MODE=fake"):
        validate_startup_config(s)


def test_production_rejects_mock_image() -> None:
    s = _prod(image_provider="mock")
    with pytest.raises(RuntimeError, match="STUDIO_IMAGE_PROVIDER=mock"):
        validate_startup_config(s)


def test_production_rejects_mock_video_and_audio() -> None:
    s = _prod(video_provider="mock")
    with pytest.raises(RuntimeError, match="STUDIO_VIDEO_PROVIDER=mock"):
        validate_startup_config(s)
    s = _prod(audio_provider="mock")
    with pytest.raises(RuntimeError, match="STUDIO_AUDIO_PROVIDER=mock"):
        validate_startup_config(s)


def test_production_allows_real_providers() -> None:
    validate_startup_config(_prod())  # must not raise


def test_development_allows_fake_mock() -> None:
    s = Settings(_env_file=None, app_env="development", llm_mode="fake", image_provider="mock")
    validate_startup_config(s)  # must not raise


def test_invalid_llm_mode_fails_settings_construction() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_mode="bogus")


def test_invalid_video_provider_fails_settings_construction() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, video_provider="bogus")


def test_invalid_app_env_fails_settings_construction() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")


def test_env_example_has_no_real_secrets() -> None:
    path = Path(__file__).resolve().parent.parent / ".env.example"
    assert path.exists(), "backend/.env.example must exist (P1-E5-T01)"
    text = path.read_text(encoding="utf-8")
    # Secret lines are present but EMPTY (template), and no real key material leaks.
    assert "STUDIO_LLM_API_KEY=" in text
    assert "STUDIO_AGNES_API_KEY=" in text
    assert not any(
        pat in text
        for pat in ("sk-", "AKIA", "AIza", "ghp_", "Bearer ", "secret_token_value")
    )


def test_image_save_rejects_invalid_provider_422(client: TestClient) -> None:
    resp = client.put("/api/v1/image/config", json={"provider": "bogus"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"


def test_image_save_rejects_invalid_video_provider_422(client: TestClient) -> None:
    resp = client.put("/api/v1/image/config", json={"video_provider": "bogus"})
    assert resp.status_code == 422


def test_llm_save_rejects_invalid_mode_422(client: TestClient) -> None:
    resp = client.put("/api/v1/llm/config", json={"mode": "bogus"})
    assert resp.status_code == 422
