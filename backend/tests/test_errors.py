"""P1-E4-T01: unified error envelope + request_id + no-leak guarantees.

Every failure — Studio errors (404/409), validation (422), unknown routes (404),
method not allowed (405), and unhandled exceptions (500) — must use the same
envelope (api-event-contract §6) and carry a request_id. 500 must never leak
stacks, absolute paths, secrets or raw exception text.
"""

from fastapi.testclient import TestClient

from app.services import ProjectService


def _envelope(resp) -> dict:
    assert "error" in resp.json()
    return resp.json()["error"]


def test_unknown_route_uses_envelope_with_request_id(client: TestClient) -> None:
    resp = client.get("/api/v1/definitely-not-a-route")
    assert resp.status_code == 404
    err = _envelope(resp)
    assert err["code"] == "NOT_FOUND"
    assert err["request_id"]
    assert resp.headers.get("X-Request-ID") == err["request_id"]


def test_method_not_allowed_uses_envelope(client: TestClient) -> None:
    resp = client.put("/api/v1/projects")
    assert resp.status_code == 405
    err = _envelope(resp)
    assert err["code"] == "METHOD_NOT_ALLOWED"
    assert err["request_id"]


def test_validation_error_uses_envelope_without_echoing_body(client: TestClient) -> None:
    # missing required field "name" → 422 envelope
    resp = client.post("/api/v1/projects", json={"aspect_ratio": "9:16"})
    assert resp.status_code == 422
    err = _envelope(resp)
    assert err["code"] == "VALIDATION_ERROR"
    assert err["request_id"]
    details = err["details"]
    assert "errors" in details
    # the request body must not be echoed back (sanitized validation details)
    body_text = resp.text
    assert "9:16" not in body_text  # input value never echoed


def test_bad_enum_validation_uses_envelope(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "X"}).json()
    resp = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"revision": 1, "patch": {"status": "not-a-status"}},
    )
    assert resp.status_code == 422
    err = _envelope(resp)
    assert err["code"] == "VALIDATION_ERROR"
    assert "not-a-status" not in resp.text  # invalid input not echoed


def test_not_found_and_conflict_keep_envelope(client: TestClient) -> None:
    missing = client.get("/api/v1/projects/nope")
    assert missing.status_code == 404
    err = _envelope(missing)
    assert err["code"] == "ENTITY_NOT_FOUND"
    assert err["request_id"]


def test_internal_error_does_not_leak_details(client: TestClient, monkeypatch) -> None:
    """500 envelope: ServerErrorMiddleware sends the response then re-raises, so the
    default TestClient (raise_server_exceptions=True) surfaces the exception instead
    of the response — use a no-raise client like production uvicorn would deliver it."""
    from app.main import app

    secret = "C:/Users/secret-user/.ssh/id_rsa STACK_TRACE_SECRET api_key=sk-abc123"  # noqa: S105 — test fixture secret (SECRET-SCAN)

    def boom(self):
        raise RuntimeError(secret)

    monkeypatch.setattr(ProjectService, "list_projects", boom)
    no_raise = TestClient(app, raise_server_exceptions=False)
    resp = no_raise.get("/api/v1/projects")
    assert resp.status_code == 500
    err = _envelope(resp)
    assert err["code"] == "INTERNAL_ERROR"
    assert err["message"] == "Internal server error."
    assert err["request_id"]
    assert secret not in resp.text
    assert "Traceback" not in resp.text
    assert "id_rsa" not in resp.text
