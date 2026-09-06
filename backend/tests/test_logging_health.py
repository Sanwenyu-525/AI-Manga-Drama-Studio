"""P1-E4-T03: correlated logging + deep health check.

- Every log line carries correlation_id / project_id / run_id / generation_id.
- Request / Agent / Generation bindings are run-local (contextvars).
- Logs never carry session tokens, api keys, or full source_text (AC2).
- /health reports database + worker + event_bus + providers; worker-stopped
  or unusable configured provider yields degraded, never healthy (AC3/AC4).
"""

import logging

from fastapi.testclient import TestClient

from app.core import logging as studio_logging


def test_filter_injects_all_fields(caplog) -> None:
    logger = studio_logging.get_logger("test.correlation")
    corr = studio_logging.set_correlation_id("req_1")
    proj = studio_logging.set_project_id("proj_1")
    run = studio_logging.set_run_id("run_1")
    gen = studio_logging.set_generation_id("gen_1")
    try:
        with caplog.at_level(logging.INFO, logger="test.correlation"):
            logger.info("hello")
    finally:
        studio_logging.reset_generation_id(gen)
        studio_logging.reset_run_id(run)
        studio_logging.reset_project_id(proj)
        studio_logging.reset_correlation_id(corr)
    assert caplog.records, "expected a captured log record"
    record = caplog.records[-1]
    assert record.correlation_id == "req_1"
    assert record.project_id == "proj_1"
    assert record.run_id == "run_1"
    assert record.generation_id == "gen_1"


def test_filter_defaults_are_dash(caplog) -> None:
    logger = studio_logging.get_logger("test.correlation.defaults")
    with caplog.at_level(logging.INFO, logger="test.correlation.defaults"):
        logger.info("no binding")
    record = caplog.records[-1]
    assert record.correlation_id == "-"
    assert record.project_id == "-"
    assert record.run_id == "-"
    assert record.generation_id == "-"


def test_correlation_scope_binds_and_resets() -> None:
    assert studio_logging.get_correlation_id() == "-"
    with studio_logging.correlation_scope("req_x", project_id="p", run_id="r"):
        assert studio_logging.get_correlation_id() == "req_x"
        assert studio_logging.get_project_id() == "p"
        assert studio_logging.get_run_id() == "r"
    assert studio_logging.get_correlation_id() == "-"
    assert studio_logging.get_project_id() == "-"
    assert studio_logging.get_run_id() == "-"


def test_health_reports_all_components(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert set(("status", "database", "worker", "event_bus", "providers")) <= set(body)
    assert body["database"] == "healthy"
    assert body["worker"] in ("healthy", "stopped")
    assert body["event_bus"] in ("healthy", "degraded")
    assert isinstance(body["providers"], dict) and body["providers"]
    if body["database"] == "healthy" and body["worker"] == "healthy" and body["event_bus"] == "healthy":
        assert body["status"] in ("healthy", "degraded")
    else:
        assert body["status"] in ("degraded", "unhealthy")


def test_health_worker_stopped_is_degraded(client: TestClient, monkeypatch) -> None:
    from app.generations import worker as worker_module

    monkeypatch.setattr(worker_module, "last_heartbeat", 0.0)
    body = client.get("/api/v1/health").json()
    assert body["worker"] == "stopped"
    assert body["status"] in ("degraded", "unhealthy")


def test_health_gateway_stopped_is_degraded(client: TestClient, monkeypatch) -> None:
    from app.events import ws as ws_module

    monkeypatch.setattr(ws_module, "_gateway", None)
    body = client.get("/api/v1/health").json()
    assert body["event_bus"] == "degraded"
    assert body["status"] in ("degraded", "unhealthy")


def test_health_comfyui_unavailable_is_degraded(client: TestClient, monkeypatch) -> None:
    from app.core.config import settings
    from app.services.provider_health_service import reset_provider_health

    reset_provider_health()
    monkeypatch.setattr(settings, "image_provider", "comfyui")
    body = client.get("/api/v1/health").json()
    assert body["providers"].get("comfyui") == "unavailable"
    assert body["status"] in ("degraded", "unhealthy")


def test_health_never_probes_network(client: TestClient, monkeypatch) -> None:
    """Health must stay cheap: no outbound probe even for comfyui."""
    from app.core.config import settings
    from app.services import provider_health_service as health_service_module

    reset = health_service_module.reset_provider_health
    reset()

    async def _explode(provider=None):  # pragma: no cover - must never run
        raise AssertionError("health performed network I/O")

    monkeypatch.setattr(settings, "image_provider", "comfyui")
    monkeypatch.setattr(
        health_service_module.ProviderHealthService, "refresh_comfyui", _explode
    )
    body = client.get("/api/v1/health").json()
    assert body["providers"].get("comfyui") == "unavailable"


def test_logs_never_carry_session_token(client: TestClient, caplog) -> None:
    """App loggers log path only (request_logging uses request.url.path).

    NOTE: the httpx client-side access log echoes the full URL including
    ?token= — that is test-harness noise, not a server log line. Assert only
    on studio loggers (app / events / generations / jobs / agent).
    """
    from app.core.config import settings

    settings.session_token = "secret-token-xyz"  # noqa: S105 — test fixture (SECRET-SCAN)
    try:
        with caplog.at_level(logging.INFO):
            resp = client.get("/api/v1/health?token=secret-token-xyz")
        assert resp.status_code == 200
    finally:
        settings.session_token = None
    studio_text = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.split(".")[0] in {"app", "events", "generations", "jobs", "agent"}
    )
    assert "secret-token-xyz" not in studio_text


def test_validation_error_never_echoes_body(client: TestClient) -> None:
    # aspect_ratio is a free string, so force a real 422 with a wrong type.
    secret = "SOURCE_SECRET_SHOULD_NEVER_ECHO_9f8a"  # noqa: S105 — test fixture (SECRET-SCAN)
    resp = client.post("/api/v1/projects", json={"name": {"nested": secret}})
    assert resp.status_code == 422
    assert secret not in resp.text
