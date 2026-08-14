"""SQLite engine + session factory.

SQLite with WAL mode (database-v0.1 §37-38). Foreign keys enforced.
Sessions are created per-request via FastAPI dependency (api/deps.py).
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_DATABASE_PATH: Path = settings.database_path


def _configure_sqlite(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def build_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    if url.startswith("sqlite"):
        # ensure parent dir exists for file-based sqlite
        path = url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


engine = build_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
