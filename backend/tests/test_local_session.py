"""P1-E5-T02 — local session token (REST/WS) + WS Origin checks.

When a session token is configured (the Tauri shell sets STUDIO_SESSION_TOKEN at
spawn), REST requires X-Session-Token and the WS connection requires ?token=.
/health + /system/info are exempt so the shell can handshake before presenting a
token. Non-allowed WS Origins are rejected before accept. With no token
configured (dev browser / dev-shell backend), auth is off.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings

# Test fixture token — S105 hardcoded password is intentional here (a test value).
TOKEN = "test-session-token-0123456789abcdef"  # noqa: S105


def test_rest_rejects_missing_token_401(client: TestClient) -> None:
    settings.session_token = TOKEN
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "UNAUTHORIZED"
    assert err["request_id"]


def test_rest_rejects_wrong_token_401(client: TestClient) -> None:
    settings.session_token = TOKEN
    resp = client.get("/api/v1/projects", headers={"X-Session-Token": "wrong"})
    assert resp.status_code == 401


def test_rest_accepts_correct_token(client: TestClient) -> None:
    settings.session_token = TOKEN
    resp = client.get("/api/v1/projects", headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200


def test_health_is_exempt_from_auth(client: TestClient) -> None:
    settings.session_token = TOKEN
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("healthy", "degraded")


def test_system_info_is_exempt_from_auth(client: TestClient) -> None:
    settings.session_token = TOKEN
    resp = client.get("/api/v1/system/info")
    assert resp.status_code == 200


def test_auth_off_when_no_token_configured(client: TestClient) -> None:
    # conftest pins settings.session_token = None → auth disabled (dev flow).
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200


def test_ws_accepts_with_token(client: TestClient) -> None:
    settings.session_token = TOKEN
    with client.websocket_connect(f"/api/v1/events?token={TOKEN}") as ws:
        hello = ws.receive_json()
        assert hello["event_type"] == "system.connected"


def test_ws_rejects_missing_token(client: TestClient) -> None:
    settings.session_token = TOKEN
    with pytest.raises((WebSocketDisconnect, RuntimeError)):
        with client.websocket_connect("/api/v1/events") as ws:
            ws.receive_json()


def test_ws_rejects_wrong_token(client: TestClient) -> None:
    settings.session_token = TOKEN
    with pytest.raises((WebSocketDisconnect, RuntimeError)):
        with client.websocket_connect("/api/v1/events?token=wrong") as ws:
            ws.receive_json()


def test_ws_rejects_non_allowed_origin(client: TestClient) -> None:
    settings.session_token = None  # origin check is independent of the token
    with pytest.raises((WebSocketDisconnect, RuntimeError)):
        with client.websocket_connect(
            "/api/v1/events",
            headers={"origin": "http://evil.example.com"},
        ) as ws:
            ws.receive_json()


def test_ws_accepts_allowed_origin(client: TestClient) -> None:
    settings.session_token = None
    with client.websocket_connect(
        "/api/v1/events",
        headers={"origin": "http://127.0.0.1:17821"},
    ) as ws:
        hello = ws.receive_json()
        assert hello["event_type"] == "system.connected"
