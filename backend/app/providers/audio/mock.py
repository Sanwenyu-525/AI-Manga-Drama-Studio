"""MockAudioProvider (TASK-012) — deterministic speech-shaped WAV for dev/test.

Pure stdlib (`wave` + `math`): a 22.05 kHz mono 16-bit PCM file whose duration is
proportional to the text length and whose tone frequency derives from
text+voice — so tests are deterministic (same input → same bytes) and CI needs
no model, no key, no network. Output is a genuine playable audio file that goes
through the normal asset pipeline, mirroring MockImageProvider's role.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import struct
import uuid
import wave

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.audio.base import AudioRequest, AudioResult

logger = get_logger("providers.audio.mock")

SAMPLE_RATE = 22050
# ~4.2 chars/second is roughly conversational Chinese narration pace; clamped so
# empty/edge inputs still produce a valid short file.
CHARS_PER_SECOND = 4.2
MIN_DURATION = 0.6
MAX_DURATION = 60.0


def mock_speech_duration(text: str) -> float:
    return max(MIN_DURATION, min(MAX_DURATION, len(text) / CHARS_PER_SECOND + MIN_DURATION / 2))


class MockAudioProvider:
    """AudioProvider protocol implementation — deterministic sine "narration"."""

    name = "mock"

    def __init__(self) -> None:
        self._output_dir = settings.data_dir / "audio_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, request: AudioRequest, on_progress) -> AudioResult:
        text = request.text or ""
        voice = request.voice or "mock-narrator"
        duration = mock_speech_duration(text)
        out_path = self._output_dir / f"vo_{uuid.uuid4().hex[:8]}.wav"

        on_progress(5, "synthesizing")
        digest = hashlib.md5(f"{voice}:{text}".encode()).digest()
        base_freq = 180 + digest[0] % 140  # 180–319 Hz voice-ish band, deterministic per input
        syllable_hz = 3.0 + (digest[1] % 20) / 10.0  # speech-like amplitude envelope
        n_samples = int(round(duration * SAMPLE_RATE))
        step = max(1, n_samples // 40)

        await asyncio.sleep(0)
        frames = bytearray()
        for i in range(n_samples):
            t = i / SAMPLE_RATE
            envelope = 0.55 + 0.45 * math.sin(2 * math.pi * syllable_hz * t)
            fade = min(1.0, t / 0.08, max(0.0, (duration - t) / 0.12))
            sample = math.sin(2 * math.pi * base_freq * t) * envelope * fade * 0.55
            frames += struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
            if i % step == 0:
                on_progress(min(95, round(i / n_samples * 95) + 5), "synthesizing")
                await asyncio.sleep(0)

        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(bytes(frames))

        on_progress(100, "saved")
        logger.info(
            "mock audio: %s (%.2fs, %d samples, voice=%s)", out_path.name, duration, n_samples, voice
        )
        return AudioResult(
            success=True,
            output_path=str(out_path),
            duration=round(duration, 3),
            extra={"engine": "mock-sine", "sample_rate": SAMPLE_RATE, "samples": n_samples},
        )

    async def cancel(self, provider_ref: str) -> None:
        logger.info("mock audio cancel (no-op): %s", provider_ref)
