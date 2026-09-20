"""Regression tests for local API authentication."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.config import settings
from app.services.auth import ApiTokenMiddleware


def _make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(ApiTokenMiddleware)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/private")
    def private():
        return {"status": "protected"}

    @app.options("/api/private")
    def private_options():
        return {"status": "ok"}

    return TestClient(app)


def test_health_is_public_when_auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "test-token")

    response = _make_client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_route_requires_header_token(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "test-token")

    response = _make_client().get("/api/private")

    assert response.status_code == 401


def test_query_string_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "test-token")

    response = _make_client().get("/api/private?token=test-token")

    assert response.status_code == 401


def test_header_token_authenticates_protected_route(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "test-token")

    response = _make_client().get(
        "/api/private",
        headers={"X-CyberMirror-Token": "test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "protected"}


def test_auth_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", False)

    response = _make_client().get("/api/private")

    assert response.status_code == 200


def test_options_preflight_bypasses_auth(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "test-token")

    response = _make_client().options("/api/private")

    assert response.status_code == 200


def test_real_health_payload_never_contains_api_token(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(routes, "load_runtime", lambda: {"username_scan_limit": 10})
    monkeypatch.setattr(routes, "wmn_status", lambda: {"loaded": False})

    payload = routes.health()

    assert payload["status"] == "ok"
    assert payload["api_auth_enabled"] is True
    assert "api_token" not in payload
