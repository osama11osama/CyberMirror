"""Bundled UI serving: runtime token bootstrap and SPA fallback."""

import pytest
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import settings


@pytest.fixture()
def ui_dist(tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>CM</title></head>"
        "<body><cm-root></cm-root></body></html>",
        encoding="utf-8",
    )
    (dist / "main.js").write_text("console.log('ok');", encoding="utf-8")

    import app.api.routes as routes

    monkeypatch.setattr(routes, "_resolve_ui_dir", lambda: dist)
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "docker-ui-token")
    return dist


def test_runtime_js_bootstraps_api_token(ui_dist, monkeypatch):
    client = TestClient(create_app())
    response = client.get("/cybermirror-runtime.js")
    assert response.status_code == 200
    body = response.text
    assert 'apiBase' in body and "/api" in body
    assert "docker-ui-token" in body
    assert "api_token" not in client.get("/api/health").json()


def test_spa_fallback_serves_index_for_client_routes(ui_dist):
    client = TestClient(create_app())
    for path in ("/dashboard", "/history", "/scan/abc"):
        response = client.get(path)
        assert response.status_code == 200
        assert "cm-root" in response.text
        assert "/cybermirror-runtime.js" in response.text

    asset = client.get("/main.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text
