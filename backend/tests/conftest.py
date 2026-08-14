"""Pytest fixtures: isolated SQLite DB per test + FastAPI TestClient with overridden session."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db import models  # noqa: F401 — register all models on Base.metadata
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_studio.db"


@pytest.fixture()
def session_factory(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory, engine


@pytest.fixture()
def client(session_factory) -> Generator[TestClient, None, None]:
    factory, _ = session_factory

    # Route background operation jobs to the same isolated DB (not the real studio.db).
    from app.db import session as db_session_module
    from app.llm import factory as llm_factory

    original_provider = db_session_module.session_factory_provider
    db_session_module.session_factory_provider = lambda: factory

    def override_get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    db_session_module.session_factory_provider = original_provider
    llm_factory.reset_gateway()
    from app.providers import registry as provider_registry

    provider_registry.reset_providers()
