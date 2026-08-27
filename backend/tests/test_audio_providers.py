"""TASK-012 tests — AudioProvider contract: mock determinism, registry wiring,
and the edge-tts adapter contract (via an injected communicate factory — no network)."""
import wave

import pytest

from app.core.config import settings
from app.core.errors import ValidationError
from app.providers.audio.edge import EdgeTTSAudioProvider, validate_rate
from app.providers.audio.mock import MockAudioProvider, mock_speech_duration


# ------------------------------------------------------------------ mock

def test_mock_produces_playable_deterministic_wav(tmp_path) -> None:
    settings.data_dir = tmp_path  # isolate outputs per-test
    provider = MockAudioProvider()

    from app.providers.audio.base import AudioRequest

    def run(text: str, voice: str):
        return _sync(provider.synthesize(AudioRequest(text=text, voice=voice), lambda p, s: None))

    r1 = run("同一句话", "zh-CN-XiaoxiaoNeural")
    r2 = run("同一句话", "zh-CN-XiaoxiaoNeural")
    r3 = run("另一句更长的台词内容明显不同", "zh-CN-XiaoxiaoNeural")

    assert r1.success and r2.success and r3.success
    assert r1.output_path.endswith(".wav")

    # deterministic bytes for identical input
    b1 = open(r1.output_path, "rb").read()
    b2 = open(r2.output_path, "rb").read()
    assert b1 == b2
    # different input → different duration (longer text is longer audio)
    assert r3.duration > r1.duration > 0

    with wave.open(r1.output_path, "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert abs(wav.getnframes() / wav.getframerate() - r1.duration) < 0.05


def test_mock_duration_is_bounded() -> None:
    assert mock_speech_duration("") >= 0.5
    assert mock_speech_duration("长" * 10_000) <= 60.0


def _sync(coro):
    import asyncio

    return asyncio.run(coro)


# ------------------------------------------------------------------ registry

def test_registry_resolves_and_rejects_audio_providers() -> None:
    from app.providers.registry import get_audio_provider

    assert get_audio_provider("mock").name == "mock"
    assert get_audio_provider(None).name == settings.audio_provider
    assert get_audio_provider("edge").name == "edge"
    with pytest.raises(ValidationError):
        get_audio_provider("bogus")


def test_provider_status_includes_audio_entries() -> None:
    from app.providers.registry import provider_status

    entries = {e["id"]: e for e in provider_status() if e["type"] == "audio"}
    assert set(entries) == {"audio_mock", "audio_edge"}
    assert entries["audio_mock"]["status"] == "connected"
    assert entries["audio_mock"]["capabilities"]["audio_generation"] is True


# ------------------------------------------------------------------ edge adapter

def test_edge_rate_validation() -> None:
    assert validate_rate("+10%") == "+10%"
    assert validate_rate("-35%") == "-35%"
    assert validate_rate(None) is None
    with pytest.raises(ValueError):
        validate_rate("fast")
    with pytest.raises(ValueError):
        validate_rate("++20%")


def test_edge_contract_with_injected_transport(tmp_path) -> None:
    """No network: the Communicate call is captured by a stub factory."""
    settings.data_dir = tmp_path
    provider = EdgeTTSAudioProvider()
    captured = {}

    async def fake_communicate(*, text, voice, rate, output_path):
        captured.update({"text": text, "voice": voice, "rate": rate, "output_path": output_path})
        with open(output_path, "wb") as f:  # noqa: ASYNC230 — stub transport, no real IO concern
            f.write(b"ID3fakemp3")

    provider._communicate_factory = fake_communicate

    from app.providers.audio.base import AudioRequest

    result = _sync(
        provider.synthesize(AudioRequest(text="你好世界", voice="zh-CN-YunxiNeural", rate="+20%"), lambda p, s: None)
    )
    assert result.success
    assert captured["text"] == "你好世界"
    assert captured["voice"] == "zh-CN-YunxiNeural"
    assert captured["rate"] == "+20%"
    assert captured["output_path"].endswith(".mp3")
    assert result.extra["voice"] == "zh-CN-YunxiNeural"


def test_edge_empty_text_and_bad_rate_fail_cleanly(tmp_path) -> None:
    settings.data_dir = tmp_path
    provider = EdgeTTSAudioProvider()

    from app.providers.audio.base import AudioRequest

    bad_rate = _sync(provider.synthesize(AudioRequest(text="x", rate="+bad"), lambda p, s: None))
    assert not bad_rate.success and "rate" in bad_rate.error

    empty = _sync(provider.synthesize(AudioRequest(text="   "), lambda p, s: None))
    assert not empty.success and "empty" in empty.error.lower()


def test_edge_missing_package_message(tmp_path, monkeypatch) -> None:
    """Lazy import failure must surface one actionable error (no crash elsewhere)."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "edge_tts":
            raise ImportError("No module named 'edge_tts'")
        return real_import(name, *args, **kwargs)

    settings.data_dir = tmp_path
    provider = EdgeTTSAudioProvider()
    provider._communicate_factory = None  # force the lazy module load path
    monkeypatch.setattr(builtins, "__import__", fake_import)

    from app.providers.audio.base import AudioRequest

    result = _sync(provider.synthesize(AudioRequest(text="hi"), lambda p, s: None))
    assert not result.success
    assert "pip install edge-tts" in result.error
