"""AudioProvider protocol (TASK-012) — the audio member of the adapter family.

This is the Studio Domain Contract for speech/music synthesis (backend-architecture
§38 adapter family): business code only ever sees this interface — never a concrete
provider (red line: GenerationService must not know specific models, and providers
must not know Episode/Scene/Shot semantics).

Concrete engines behind the registry (registry.get_audio_provider):
  mock : MockAudioProvider      — deterministic WAV sine (dev/test default, no deps/network)
  edge : EdgeTTSAudioProvider   — Microsoft Edge online neural voices via the
                                  edge-tts package (https://github.com/rany2/edge-tts,
                                  LGPL-3.0, ~11.8k stars; optional runtime dep)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AudioRequest:
    """Normalized Studio-side synthesis request — provider-agnostic."""

    text: str
    voice: str | None = None  # provider-specific voice id; None → studio/default
    rate: str | None = None  # speaking rate, e.g. "+10%" | "-5%" (validated upstream)
    metadata: dict = field(default_factory=dict)


@dataclass
class AudioResult:
    """Normalized synthesis result — provider-agnostic."""

    success: bool
    output_path: str | None = None  # absolute path to the synthesized audio file
    duration: float | None = None  # seconds (None when the engine cannot cheaply know)
    provider_ref: str | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


class AudioProvider(Protocol):
    name: str

    async def synthesize(self, request: AudioRequest, on_progress) -> AudioResult:
        """Synthesize one utterance; on_progress(percent: int, stage: str) during the run."""
        ...

    async def cancel(self, provider_ref: str) -> None:
        """Best-effort cancel of a running synthesis."""
        ...
