"""AudioService (TASK-012) — the timeline-clip → voiceover-generation boundary.

Mirrors RenderService: queues voiceover synthesis as a type="audio" Generation
(the generation queue IS the job queue); the worker executes it through an
AudioProvider and registers the produced file as an immutable AUDIO asset under
"vg:clip:{clip_id}:AUDIO", then rebinds the VOICE clip to the newest version
(same semantics as replace-asset).

Red lines respected: this Service owns all clip/track semantics; providers never
see Episode/Scene/Shot meaning, and the API router stays thin.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Asset, Generation
from app.domain.generation import VoiceoverBatchItem, VoiceoverBatchResult, VoiceoverGenerateRequest
from app.events.bus import EVENT_GENERATION_QUEUED, StudioEvent, bus
from app.repositories import TimelineRepository

logger = get_logger("audio")

RATE_PATTERN = re.compile(r"^[+-]\d{1,3}%$")
MAX_VOICEOVER_TEXT = 4000


def clip_audio_version_group(clip_id: str) -> str:
    """Immutable AUDIO version group of one VOICE clip (ADR-001 style)."""
    return "vg:clip:" + clip_id + ":AUDIO"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AudioService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.timelines = TimelineRepository(session)

    def create_voiceover_generation(self, clip_id: str, data: VoiceoverGenerateRequest) -> Generation:
        """Queue a type="audio" generation for one VOICE-track clip (202 path)."""
        clip = self.timelines.get_clip(clip_id)
        if clip is None:
            raise NotFoundError("Clip does not exist.", {"clip_id": clip_id})
        timeline = self.timelines.get(clip.timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": clip.timeline_id})
        track = self.timelines.get_track(clip.track_id)
        if track is None or track.track_type != "VOICE":
            raise ValidationError(
                "Voiceover can only be generated for clips on a VOICE track.",
                {"clip_id": clip_id, "track_type": getattr(track, "track_type", None)},
            )

        text = (data.text or "").strip() or (clip.text or "").strip()
        if not text:
            raise ValidationError(
                "Voiceover has no text. Set clip.text or pass text in the request.",
                {"clip_id": clip_id},
            )
        if len(text) > MAX_VOICEOVER_TEXT:
            raise ValidationError(
                f"Voiceover text exceeds {MAX_VOICEOVER_TEXT} characters.",
                {"clip_id": clip_id, "length": len(text)},
            )
        if data.rate is not None and not RATE_PATTERN.match(data.rate):
            raise ValidationError("rate must look like '+10%' or '-5%'.", {"rate": data.rate})

        # Unknown provider ids fail fast BEFORE queuing (same rule as image).
        # Function-level import mirrors generation_service (avoids the
        # registry ↔ services package-import cycle).
        from app.providers.registry import get_audio_provider

        pid = data.provider  # None resolves to settings.audio_provider inside the registry
        get_audio_provider(pid)

        parameters = json.dumps(
            {
                "text": text,
                "voice": data.voice,
                "rate": data.rate,
                "timeline_clip_id": clip.id,
                "timeline_id": timeline.id,
                "episode_id": timeline.episode_id,
            },
            ensure_ascii=False,
        )
        generation = Generation(
            project_id=timeline.project_id,
            shot_id=clip.shot_id,
            type="audio",
            provider=pid or _resolved_default_provider_id(),
            status="queued",
            parameters=parameters,
            progress=0,
            stage="queued",
            max_attempts=1,
        )
        self.session.add(generation)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_QUEUED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=timeline.project_id,
                payload={
                    "type": "audio",
                    "timeline_clip_id": clip.id,
                    "voiceover_text_head": text[:50],
                },
            )
        )
        logger.info(
            "voiceover generation queued: %s (clip %s, provider %s, %d chars)",
            generation.id, clip_id, generation.provider, len(text),
        )
        return generation

    def create_voiceover_batch(self, timeline_id: str) -> VoiceoverBatchResult:
        """C1 整轨批量配音: queue a voiceover for every VOICE-track clip with text.

        Reuses create_voiceover_generation per clip (same 202 semantics, one
        type="audio" generation + queued event each). Skips:
        - clips already bound to an AUDIO asset (won't re-generate → already_bound)
        - VOICE clips without text (→ skipped_no_text)
        """
        timeline = self.timelines.get(timeline_id)
        if timeline is None:
            raise NotFoundError("Timeline does not exist.", {"timeline_id": timeline_id})

        submitted: list[VoiceoverBatchItem] = []
        skipped_no_text: list[str] = []
        already_bound: list[str] = []

        for clip in self.timelines.list_clips(timeline_id):
            if getattr(clip, "enabled", 1) == 0:
                continue
            track = self.timelines.get_track(clip.track_id)
            if track is None or track.track_type != "VOICE":
                continue
            if self._clip_has_audio(clip):
                already_bound.append(clip.id)
                continue
            text = (clip.text or "").strip()
            if not text:
                skipped_no_text.append(clip.id)
                continue
            gen = self.create_voiceover_generation(
                clip.id, VoiceoverGenerateRequest(text=text)
            )
            submitted.append(
                VoiceoverBatchItem(
                    clip_id=clip.id,
                    generation_id=gen.id,
                    text_head=text[:50],
                )
            )

        logger.info(
            "voiceover batch for timeline %s: %d queued, %d no-text, %d already-bound",
            timeline_id, len(submitted), len(skipped_no_text), len(already_bound),
        )
        return VoiceoverBatchResult(
            timeline_id=timeline_id,
            submitted=submitted,
            skipped_no_text=skipped_no_text,
            already_bound=already_bound,
        )

    def _clip_has_audio(self, clip) -> bool:
        """True when the clip is already bound to an AUDIO asset (has a voiceover)."""
        if not clip.asset_id:
            return False
        asset = self.session.get(Asset, clip.asset_id)
        return asset is not None and asset.type == "audio"


def _resolved_default_provider_id() -> str:
    from app.core.config import settings

    return settings.audio_provider
