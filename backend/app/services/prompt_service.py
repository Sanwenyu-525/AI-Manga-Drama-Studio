"""PromptService (ADR-002): versioned prompts for shots (and later characters/locations).

- prompts.active_version_id is the authoritative active version.
- prompt_versions are immutable: edits create vN+1 (max+1 + unique index backstop).
- For SHOT targets the deprecated shot.image_prompt/video_prompt/negative_prompt
  columns are kept in sync as a write-through cache (frontend reads them until it
  switches to the prompt APIs); shot.active_prompt_version_id is the convenience
  pointer to the active SHOT_IMAGE version.
- commit=False lets callers own the transaction (shot update path).
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models import Prompt, PromptVersion, Shot

SHOT_TARGET = "SHOT"
CACHE_COLUMNS = {"SHOT_IMAGE": "image_prompt", "SHOT_VIDEO": "video_prompt"}


class PromptService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- queries ---

    def get_prompt(self, target_type: str, target_id: str, prompt_type: str) -> Prompt | None:
        return self.session.scalar(
            select(Prompt).where(
                Prompt.target_type == target_type,
                Prompt.target_id == target_id,
                Prompt.prompt_type == prompt_type,
            )
        )

    def get_prompt_by_id(self, prompt_id: str) -> Prompt:
        prompt = self.session.get(Prompt, prompt_id)
        if prompt is None:
            raise NotFoundError("Prompt does not exist.", {"prompt_id": prompt_id})
        return prompt

    def list_shot_prompts(self, shot_id: str) -> list[Prompt]:
        return list(
            self.session.scalars(
                select(Prompt)
                .where(Prompt.target_type == SHOT_TARGET, Prompt.target_id == shot_id)
                .order_by(Prompt.prompt_type)
            )
        )

    def list_versions(self, prompt_id: str) -> list[PromptVersion]:
        prompt = self.session.get(Prompt, prompt_id)
        if prompt is None:
            raise NotFoundError("Prompt does not exist.", {"prompt_id": prompt_id})
        return list(
            self.session.scalars(
                select(PromptVersion)
                .where(PromptVersion.prompt_id == prompt_id)
                .order_by(PromptVersion.version_number.desc())
            )
        )

    def get_active_version(self, prompt: Prompt) -> PromptVersion | None:
        if prompt.active_version_id is None:
            return None
        return self.session.get(PromptVersion, prompt.active_version_id)

    # --- mutations ---

    def create_version(
        self,
        *,
        project_id: str,
        target_type: str,
        target_id: str,
        prompt_type: str,
        positive: str | None,
        negative: str | None = None,
        structured_spec: dict | None = None,
        provider: str | None = None,
        model: str | None = None,
        generated_by: str = "user",
        commit: bool = True,
    ) -> PromptVersion:
        """Create a new prompt version (v1 when the prompt row is missing)."""
        prompt = self.get_prompt(target_type, target_id, prompt_type)
        if prompt is None:
            prompt = Prompt(
                project_id=project_id,
                target_type=target_type,
                target_id=target_id,
                prompt_type=prompt_type,
            )
            self.session.add(prompt)
            self.session.flush()
        version_number = self._next_version_number(prompt.id)
        version = PromptVersion(
            prompt_id=prompt.id,
            version_number=version_number,
            positive_prompt=positive,
            negative_prompt=negative,
            structured_spec_json=json.dumps(structured_spec, ensure_ascii=False) if structured_spec else None,
            provider=provider,
            model=model,
            generated_by=generated_by,
        )
        self.session.add(version)
        self.session.flush()  # assign version.id before wiring pointers
        prompt.active_version_id = version.id
        if target_type == SHOT_TARGET:
            self._sync_shot_cache(target_id, prompt_type, positive, negative, version.id)
        if commit:
            self.session.commit()
        return version

    def activate_version(self, version_id: str, commit: bool = True) -> PromptVersion:
        version = self.session.get(PromptVersion, version_id)
        if version is None:
            raise NotFoundError("Prompt version does not exist.", {"version_id": version_id})
        prompt = self.session.get(Prompt, version.prompt_id)
        if prompt is None:
            raise NotFoundError("Prompt does not exist.", {"prompt_id": version.prompt_id})
        prompt.active_version_id = version.id
        if prompt.target_type == SHOT_TARGET:
            self._sync_shot_cache(prompt.target_id, prompt.prompt_type, version.positive_prompt, version.negative_prompt, version.id)
        if commit:
            self.session.commit()
        return version

    def _sync_shot_cache(self, shot_id: str, prompt_type: str, positive: str | None, negative: str | None, version_id: str) -> None:
        """Write-through to the deprecated shot columns + convenience pointer (ADR-002 2.3)."""
        shot = self.session.get(Shot, shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        if prompt_type in CACHE_COLUMNS:
            setattr(shot, CACHE_COLUMNS[prompt_type], positive)
        if negative is not None:
            shot.negative_prompt = negative
        if prompt_type == "SHOT_IMAGE":
            shot.active_prompt_version_id = version_id

    def _next_version_number(self, prompt_id: str) -> int:
        current = self.session.scalar(
            select(func.max(PromptVersion.version_number)).where(PromptVersion.prompt_id == prompt_id)
        )
        return (current or 0) + 1

    # --- validation helpers ---

    def require_valid_type(self, prompt_type: str) -> None:
        from app.db.models.prompt import PROMPT_TYPES

        if prompt_type not in PROMPT_TYPES:
            raise ValidationError("Unsupported prompt type.", {"prompt_type": prompt_type})
