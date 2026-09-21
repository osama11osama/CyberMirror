"""Shared fixtures for integration tests (isolated temp DB, no live OSINT)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.config import settings
from app.storage import database as db


@pytest.fixture()
def isolated_app(tmp_path, monkeypatch):
    """Fresh SQLite + auth token for each test; no real OSINT network calls required."""
    db_path = tmp_path / "integration.sqlite3"
    monkeypatch.setattr(settings, "database_path", db_path)
    monkeypatch.setattr(settings, "exports_dir", tmp_path / "exports")
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "logs_dir", tmp_path / "logs")
    monkeypatch.setattr(settings, "encryption_enabled", True)
    monkeypatch.setattr(settings, "encryption_key", None)
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "integration-test-token")
    monkeypatch.setattr(settings, "playwright_enabled", False)

    from app.services import crypto
    from app.services import runtime_settings

    monkeypatch.setattr(crypto, "_KEY_FILE", tmp_path / ".encryption_key")
    monkeypatch.setattr(
        runtime_settings, "RUNTIME_FILE", tmp_path / "runtime_settings.json"
    )

    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    db.init_db()

    # Avoid scheduler side effects during tests.
    monkeypatch.setattr(routes, "start_scheduler", lambda: None)
    monkeypatch.setattr(routes, "_resolve_ui_dir", lambda: None)

    app = routes.create_app()
    client = TestClient(app)
    headers = {"X-CyberMirror-Token": "integration-test-token"}
    return client, headers
