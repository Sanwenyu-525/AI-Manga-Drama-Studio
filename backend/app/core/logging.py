"""Structured logging setup (P1-E4-T03). Every line carries correlation ids.

Correlation flow:
- HTTP: the request-logging middleware in main.py binds the request_id via
  set_correlation_id() for the duration of the request, so every log line emitted
  while handling it (including error handlers) carries the same id that appears
  in X-Request-ID and the error envelope.
- Worker: worker_loop binds "gen:{id}" + generation_id (+ project_id once the
  row is loaded), so worker logs are traceable back to the row that produced them.
- Agent: _run_graph binds run_id + project_id (+ correlation "run:{id}").

Field contract (all default "-"; never secrets / source_text / full prompts):
  correlation_id / project_id / run_id / generation_id
Example:
  2026-08-31 12:00:00 INFO app [req_abc proj_1 - -] http GET /api/v1/health -> 200 (1.2ms)
"""

import contextvars
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import settings

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)
_project_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "project_id", default="-"
)
_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")
_generation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "generation_id", default="-"
)

_configured = False


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str) -> contextvars.Token[str]:
    """Bind a correlation id (request_id / gen id / run id). Returns a token for reset()."""
    return _correlation_id.set(value or "-")


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    _correlation_id.reset(token)


def get_project_id() -> str:
    return _project_id.get()


def set_project_id(value: str | None) -> contextvars.Token[str]:
    return _project_id.set(value or "-")


def reset_project_id(token: contextvars.Token[str]) -> None:
    _project_id.reset(token)


def get_run_id() -> str:
    return _run_id.get()


def set_run_id(value: str | None) -> contextvars.Token[str]:
    return _run_id.set(value or "-")


def reset_run_id(token: contextvars.Token[str]) -> None:
    _run_id.reset(token)


def get_generation_id() -> str:
    return _generation_id.get()


def set_generation_id(value: str | None) -> contextvars.Token[str]:
    return _generation_id.set(value or "-")


def reset_generation_id(token: contextvars.Token[str]) -> None:
    _generation_id.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Inject the contextvar values into every record (Formatter default covers unset cases)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()
        record.project_id = _project_id.get()
        record.run_id = _run_id.get()
        record.generation_id = _generation_id.get()
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
            "%(asctime)s %(levelname)s %(name)s "
            "[%(correlation_id)s %(project_id)s %(run_id)s %(generation_id)s] %(message)s",
            defaults={
                "correlation_id": "-",
                "project_id": "-",
                "run_id": "-",
                "generation_id": "-",
            },
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


@contextmanager
def correlation_scope(
    value: str,
    *,
    project_id: str | None = None,
    run_id: str | None = None,
    generation_id: str | None = None,
) -> Iterator[None]:
    """Context-manager form for ad-hoc scoping (workers, background tasks)."""
    corr_token = set_correlation_id(value)
    proj_token = set_project_id(project_id) if project_id is not None else None
    run_token = set_run_id(run_id) if run_id is not None else None
    gen_token = set_generation_id(generation_id) if generation_id is not None else None
    try:
        yield
    finally:
        if gen_token is not None:
            reset_generation_id(gen_token)
        if run_token is not None:
            reset_run_id(run_token)
        if proj_token is not None:
            reset_project_id(proj_token)
        reset_correlation_id(corr_token)
