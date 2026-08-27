"""Audio provider adapters (TASK-012) — see base.py for the Studio contract."""

from app.providers.audio.base import AudioProvider, AudioRequest, AudioResult
from app.providers.audio.edge import EdgeTTSAudioProvider
from app.providers.audio.mock import MockAudioProvider

__all__ = ["AudioProvider", "AudioRequest", "AudioResult", "EdgeTTSAudioProvider", "MockAudioProvider"]
