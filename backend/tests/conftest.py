"""Pytest fixtures: isolated SQLite DB per test + FastAPI TestClient with overridden session."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401 — register all models on Base.metadata
from app.db.base import Base
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
def client(session_factory, tmp_path: Path) -> Generator[TestClient]:
    factory, _ = session_factory

    # Route background operation jobs to the same isolated DB (not the real studio.db).
    from app.db import session as db_session_module
    from app.llm import factory as llm_factory

    original_provider = db_session_module.session_factory_provider
    db_session_module.session_factory_provider = lambda: factory

    # Isolate data_dir so developer-machine state (saved llm.json with a real
    # openai/agnes connection, agnes_output/, ...) never leaks into tests.
    from app.core.config import settings

    original_data_dir = settings.data_dir
    settings.data_dir = tmp_path / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    # Isolate env-provided api keys: 服务端已实现 env 优先语义，本机若设置了
    # STUDIO_LLM_API_KEY / STUDIO_AGNES_API_KEY，测试会读到真实密钥并可能发
    # 真实请求 —— 强制置 None，杜绝泄漏（与 data_dir 隔离同一原则）。
    original_llm_key = settings.llm_api_key
    original_agnes_key = settings.agnes_api_key
    settings.llm_api_key = None
    settings.agnes_api_key = None

    # P1-E5-T01: pin the environment so a developer machine with
    # STUDIO_APP_ENV=production can't flip on the production fail-closed gate
    # (and break the whole suite). The production gate is tested explicitly in
    # test_config.py by constructing Settings directly.
    original_app_env = settings.app_env
    settings.app_env = "development"

    # P1-E5-T02: local session auth is OFF by default in tests; individual tests
    # that exercise it set settings.session_token themselves.
    original_session_token = settings.session_token
    settings.session_token = None

    def override_get_db() -> Generator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # P7-T004: rebuild the Director graph with an ISOLATED (in-memory) checkpointer
    # per test so proposal interrupt/resume never reads a shared/disk-backed store.
    from app.agents.director import graph as director_graph_module
    from app.agents.checkpointers.sqlite_saver import SqliteCheckpointSaver

    original_director_graph = director_graph_module.director_graph

    def _fresh_isolated_graph():
        return director_graph_module.build_director_graph(checkpointer=SqliteCheckpointSaver())

    director_graph_module.director_graph = _fresh_isolated_graph()

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        director_graph_module.director_graph = original_director_graph
        db_session_module.session_factory_provider = original_provider
        settings.data_dir = original_data_dir
        settings.app_env = original_app_env
        settings.session_token = original_session_token
        settings.llm_api_key = original_llm_key
        settings.agnes_api_key = original_agnes_key
        llm_factory.reset_gateway()
        from app.providers import registry as provider_registry

        provider_registry.reset_providers()
        from app.services.provider_health_service import reset_provider_health

        reset_provider_health()
