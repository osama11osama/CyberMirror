"""Regression tests for encrypted-profile graph generation."""

from fastapi.testclient import TestClient

from app.api.routes import create_app, scan_graph
from app.config import settings
from app.models.schemas import IdentityProfile
from app.storage.database import create_scan, get_scan, init_db


PROFILE = IdentityProfile(
    full_name="Jane Doe",
    username="janedoe",
    email="jane@example.com",
)


def _prepare_db(monkeypatch, tmp_path, *, encryption_enabled: bool) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "graph-test.sqlite3")
    monkeypatch.setattr(settings, "encryption_enabled", encryption_enabled)
    monkeypatch.setattr(settings, "encryption_key", "graph-regression-key-32bytes!")
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "test-token")
    init_db()


def _assert_plaintext_graph(payload: dict) -> None:
    labels = [node["label"] for node in payload["nodes"]]
    assert "Jane Doe" in labels
    assert "janedoe" in labels
    assert "jane@example.com" in labels
    assert all(not label.startswith("gAAAA") for label in labels)


def test_graph_decrypts_encrypted_profile(monkeypatch, tmp_path):
    _prepare_db(monkeypatch, tmp_path, encryption_enabled=True)
    scan_id = create_scan(PROFILE, ["web_search"])

    stored = get_scan(scan_id)["scan"]["profile_json"]
    assert stored.startswith("gAAAA")
    assert "jane@example.com" not in stored

    graph = scan_graph(scan_id)
    _assert_plaintext_graph(graph.model_dump())


def test_graph_works_when_encryption_is_disabled(monkeypatch, tmp_path):
    _prepare_db(monkeypatch, tmp_path, encryption_enabled=False)
    scan_id = create_scan(PROFILE, ["web_search"])

    stored = get_scan(scan_id)["scan"]["profile_json"]
    assert stored.startswith("{")
    assert "jane@example.com" in stored

    graph = scan_graph(scan_id)
    _assert_plaintext_graph(graph.model_dump())


def test_graph_endpoint_returns_decrypted_profile(monkeypatch, tmp_path):
    _prepare_db(monkeypatch, tmp_path, encryption_enabled=True)
    scan_id = create_scan(PROFILE, ["web_search"])

    monkeypatch.setattr("app.api.routes.start_scheduler", lambda: None)
    client = TestClient(create_app())
    response = client.get(
        f"/api/scans/{scan_id}/graph",
        headers={"X-CyberMirror-Token": "test-token"},
    )

    assert response.status_code == 200
    _assert_plaintext_graph(response.json())
