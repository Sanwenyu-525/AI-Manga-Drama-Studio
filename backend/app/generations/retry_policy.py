"""Retry policy error classification (P5-T009).

MVP error taxonomy for a failed generation:
- Retryable      — transient infra/connection failures worth re-running with backoff
                   (ProviderUnavailableError, httpx connection/timeout transport errors).
- NonRetryable   — deterministic failures that would fail again identically
                   (ComfyUIError template/workflow/no-output problems, validation and
                   file errors, an unsuccessful provider result). These go straight to
                   'failed' without burning the attempt budget.
- UserActionRequired — mapped to 'failed' with a clear error message (no new state in
                   MVP, per P5-T009). We classify it as NonRetryable so the worker stops
                   and surfaces a definitive message to the user.

The classification is a pure function over the exception type + message so it is
unit-testable without a provider (P5-T009 requirement).
"""

from __future__ import annotations

import enum

from app.core.errors import (
    ComfyUIError,
    ProviderUnavailableError,
    StudioError,
)

# ==== classification result ====

__all__ = [
    "RetryOutcome",
    "classify_failure",
]


class RetryOutcome(enum.Enum):
    """How a failed generation should be handled by the worker."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"


# Resource/keyword signals that mean "transient infrastructure hiccup", even when
# wrapped in a generic Studio error. Kept intentionally conservative — we only
# match words that clearly imply connectivity/availability.
_TRANSIENT_MARKERS = (
    "unreachable",
    "unavailable",
    "connection",
    "timed out",
    "timeout",
    "connect",
)


def classify_failure(exc: BaseException | None, message: str = "") -> RetryOutcome:
    """Decide Retryable vs NonRetryable for a worker failure.

    exc is the raw exception raised by the provider (may be None when there is no
    exception object — e.g. an unsuccessful ImageResult). message is the human text
    that will be persisted as error_message.
    """
    if exc is None:
        # No exception object: an unsuccessful result or a missing-output outcome —
        # deterministic, never worth retrying.
        return RetryOutcome.NON_RETRYABLE

    if isinstance(exc, ProviderUnavailableError):
        # ComfyUI not reachable / transport error — classic retryable.
        return RetryOutcome.RETRYABLE

    if isinstance(exc, ComfyUIError):
        # Workflow/template/execution/no-output problems are deterministic — retrying
        # would fail identically. NonRetryable.
        return RetryOutcome.NON_RETRYABLE

    # Combine the persisted message with the exception text so an exception carrying a
    # transient marker (e.g. "connection to provider lost") is caught even when the
    # caller passed message="" (the default).
    haystack = message or f"{type(exc).__name__}: {exc}"

    if isinstance(exc, StudioError):
        # Any other Studio error: unless it looks like a transient infra marker, treat
        # as deterministic.
        return RetryOutcome.RETRYABLE if _looks_transient(haystack) else RetryOutcome.NON_RETRYABLE

    # Generic / unexpected exception (validation, file IO, httpx transport leaking
    # through). httpx TransportError subclasses (ConnectTimeout, ReadTimeout,
    # ConnectError, ...) are transient by nature.
    return RetryOutcome.RETRYABLE if _looks_transient(haystack) else RetryOutcome.NON_RETRYABLE


def _looks_transient(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)
