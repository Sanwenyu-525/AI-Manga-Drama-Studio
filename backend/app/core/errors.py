"""Unified error hierarchy + error response contract.

Error response (api-event-contract §6):
    {"error": {"code": "SHOT_NOT_FOUND", "message": "...", "details": {}, "request_id": "req_xxx"}}
"""

from __future__ import annotations

from typing import Any


class StudioError(Exception):
    """Base class for all Studio errors (backend-architecture §57)."""

    code: str = "STUDIO_ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(StudioError):
    code = "ENTITY_NOT_FOUND"
    status_code = 404


class ConflictError(StudioError):
    code = "CONFLICT"
    status_code = 409


class ValidationError(StudioError):
    code = "VALIDATION_ERROR"
    status_code = 422


class AgentError(StudioError):
    code = "AGENT_ERROR"
    status_code = 500


class GenerationError(StudioError):
    code = "GENERATION_ERROR"
    status_code = 500


class ProviderError(StudioError):
    code = "PROVIDER_ERROR"
    status_code = 502


class ProviderUnavailableError(ProviderError):
    code = "PROVIDER_UNAVAILABLE"
    status_code = 503


class ComfyUIError(ProviderError):
    code = "COMFYUI_ERROR"
    status_code = 502
