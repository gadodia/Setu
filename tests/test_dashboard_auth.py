"""Password authentication for the local Setu dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from setu.dashboard.server import SESSION_COOKIE, create_app
from setu.models import Base


def _client(config) -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    return TestClient(create_app(config=config, session_factory=sessions))


def _login(client: TestClient, config):
    return client.post(
        "/api/auth/login",
        json={"password": config.dashboard_password.get_secret_value()},
    )


def test_dashboard_fails_closed_without_a_strong_configured_password(config):
    config.dashboard_password = None
    with pytest.raises(RuntimeError, match="not configured"):
        create_app(config=config)

    config.dashboard_password = SecretStr("too-short")
    with pytest.raises(RuntimeError, match="at least 12"):
        create_app(config=config)


def test_unauthenticated_browser_and_api_requests_are_blocked(config):
    client = _client(config)

    page = client.get("/", follow_redirects=False)
    api = client.get("/api/overview")

    assert page.status_code == 303
    assert page.headers["location"] == "/login"
    assert api.status_code == 401
    assert api.json() == {"detail": "Dashboard authentication required."}
    assert client.get("/login").status_code == 200
    assert client.get("/login.css").status_code == 200
    assert client.get("/login.js").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_login_creates_http_only_session_and_logout_invalidates_it(config):
    client = _client(config)

    rejected = client.post("/api/auth/login", json={"password": "incorrect-password"})
    assert rejected.status_code == 401
    assert config.dashboard_password.get_secret_value() not in rejected.text

    accepted = _login(client, config)
    cookie = accepted.headers["set-cookie"]
    assert accepted.status_code == 200
    assert accepted.json() == {"authenticated": True}
    assert f"{SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=28800" in cookie
    assert client.get("/api/overview").status_code == 200
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"

    request_token = client.get("/api/session").json()["request_token"]
    assert client.post("/api/auth/logout").status_code == 403
    logged_out = client.post(
        "/api/auth/logout",
        headers={"X-Setu-Request-Token": request_token},
    )
    assert logged_out.status_code == 200
    assert logged_out.json() == {"authenticated": False}
    assert client.get("/api/overview").status_code == 401


def test_repeated_bad_passwords_are_rate_limited(config):
    client = _client(config)

    for attempt in range(5):
        response = client.post(
            "/api/auth/login",
            json={"password": f"incorrect-password-{attempt}"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/auth/login",
        json={"password": config.dashboard_password.get_secret_value()},
    )
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_activity_websocket_requires_the_authenticated_session(config):
    client = _client(config)

    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect("/ws/activity"):
            pass
    assert rejected.value.code == 4401

    assert _login(client, config).status_code == 200
    with client.websocket_connect("/ws/activity") as socket:
        socket.close()
