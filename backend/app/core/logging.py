"""Structured logging setup. All logs carry correlation ids (request_id / run_id / generation_id)."""

import logging
import sys

from app.core.config import settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
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
