"""Structured logging setup. All logs carry correlation ids (request_id / run_id / generation_id).

Correlation flow:
- HTTP: the request-logging middleware in main.py binds the request_id via
  set_correlation_id() for the duration of the request, so every log line emitted
  while handling it (including error handlers) carries the same id that appears
  in X-Request-ID and the error envelope.
- Worker: run_generation binds "gen:{id}" while a generation executes, so worker
  logs are traceable back to the row that produced them.
"""

import contextvars
import logging
import sys
from collections.abc import Iterator

from app.core.config import settings

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)

_configured = False


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str) -> contextvars.Token[str]:
    """Bind a correlation id (request_id / gen id / run id). Returns a token for reset()."""
    return _correlation_id.set(value or "-")


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    _correlation_id.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Inject the contextvar value into every record (Formatter default covers unset cases)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()
        return True


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s",
            defaults={"correlation_id": "-"},
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    # SQLAlchemy is noisy at DEBUG; keep it at WARNING unless explicitly requested.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def correlation_scope(value: str) -> Iterator[None]:
    """Context-manager form for ad-hoc scoping (workers, background tasks)."""
    token = set_correlation_id(value)
    try:
        yield
    finally:
        reset_correlation_id(token)
