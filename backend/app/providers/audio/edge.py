"""EdgeTTSAudioProvider (TASK-012) — real online neural TTS via edge-tts.

Uses the high-star `edge-tts` package (github.com/rany2/edge-tts, ~11.8k stars,
LGPL-3.0) which speaks Microsoft Edge's Read-Aloud voices: dozens of zh-CN
neural voices, zero GPU, zero API key. Trade-offs documented in the contract
docs: it depends on an undocumented Microsoft endpoint, so it is great for
dev/prototyping but should not be the production default (cloud vendor APIs or
local CosyVoice cover that).

The dependency is imported lazily so a missing package produces one actionable
error only when an edge synthesis is actually requested — startup and tests
never need it installed.
"""

from __future__ import annotations

import asyncio
import re
import uuid

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.audio.base import AudioRequest, AudioResult

logger = get_logger("providers.audio.edge")

RATE_PATTERN = re.compile(r"^[+-]\d{1,3}%$")
VOLUME_PATTERN = re.compile(r"^[+-]\d{1,3}%$")


def validate_rate(rate: str | None) -> str | None:
    """Raise on malformed rate/volume strings before they reach edge-tts."""
    if rate is not None and not RATE_PATTERN.match(rate):
        raise ValueError("rate must look like '+10%' or '-5%'.")
    return rate


class EdgeTTSAudioProvider:
    """AudioProvider protocol implementation — MP3 via edge_tts.Communicate."""

    name = "edge"

    def __init__(self) -> None:
        self._output_dir = settings.data_dir / "audio_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._communicate_factory = None  # overridable for contract tests

    def _load_module(self):
        try:
            import edge_tts

            return edge_tts
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "STUDIO_AUDIO_PROVIDER=edge requires the 'edge-tts' package. "
                "Install it with: pip install edge-tts (or set STUDIO_AUDIO_PROVIDER=mock)."
            ) from exc

    async def synthesize(self, request: AudioRequest, on_progress) -> AudioResult:
        voice = request.voice or settings.tts_default_voice
        try:
            rate = validate_rate(request.rate)
        except ValueError as exc:
            return AudioResult(False, error=str(exc))

        text = request.text or ""
        if not text.strip():
            return AudioResult(False, error="Voiceover text is empty.")

        out_path = self._output_dir / f"vo_{uuid.uuid4().hex[:8]}.mp3"
        on_progress(5, "submitting")

        factory = self._communicate_factory or self._default_communicate
        try:
            await factory(
                text=text,
                voice=voice,
                rate=rate,
                output_path=str(out_path),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — surfaced through the failure path
            logger.warning("edge-tts failed: %s", exc)
            return AudioResult(False, error=f"edge-tts synthesis failed: {exc}")

        if not out_path.is_file() or out_path.stat().st_size == 0:
            return AudioResult(False, error="edge-tts returned no audio data.")
        on_progress(100, "saved")
        logger.info("edge tts: %s (%s, %d bytes)", out_path.name, voice, out_path.stat().st_size)
        return AudioResult(
            success=True,
            output_path=str(out_path),
            duration=None,  # mp3 duration needs a decoder; asset.duration stays None
            extra={"engine": "edge-tts", "voice": voice},
        )

    async def cancel(self, provider_ref: str) -> None:
        logger.info("edge tts cancel (best-effort no-op): %s", provider_ref)

    async def _default_communicate(self, *, text: str, voice: str, rate: str | None, output_path: str) -> None:
        module = self._load_module()
        communicate = module.Communicate(text=text, voice=voice, rate=rate or "+0%")
        await communicate.save(output_path)
