"""API integration: auth, scan lifecycle, history, settings (no live OSINT)."""

from __future__ import annotations

from app.engine.scan_engine import ScanEngine
from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingCategory, FindingOutcome
from app.services.page_analyzer import artifact_from_http
from app.services.investigation_budget import clear_budget, default_budget, get_budget


def test_health_is_public_and_reports_version(isolated_app):
    client, _headers = isolated_app
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "2.5.0"
    assert body["release_name"] == "Deep Intelligence"
    assert "api_token" not in body


def test_protected_routes_require_token(isolated_app):
    client, headers = isolated_app
    assert client.get("/api/scans").status_code == 401
    assert client.get("/api/scans", headers=headers).status_code == 200


def test_scan_create_detail_with_mocked_modules(isolated_app, monkeypatch):
    client, headers = isolated_app

    async def fake_execute(self, scan_id, profile, modules):
        return [
            Finding(
                scan_id=scan_id,
                source="username_scan",
                category=FindingCategory.USERNAME,
                platform="Example",
                title="Account verified: Example",
                url="https://example.com/u",
                confidence=0.92,
                outcome=FindingOutcome.CONFIRMED,
                verification=VerificationState.VERIFIED,
            )
        ]

    monkeypatch.setattr(ScanEngine, "_execute_modules", fake_execute)

    start = client.post(
        "/api/scans",
        headers=headers,
        json={
            "profile": {"username": "janedoe", "email": "", "full_name": ""},
            "providers": ["username_scan"],
            "async_mode": False,
        },
    )
    assert start.status_code == 200
    body = start.json()
    assert body.get("id") or body.get("status") == "completed" or "findings" in body
    scan_id = body.get("id")
    if not scan_id:
        # Sync mode may return ScanDetail
        scan_id = body.get("id")
    assert scan_id
    detail = client.get(f"/api/scans/{scan_id}", headers=headers)
    assert detail.status_code == 200
    findings = detail.json().get("findings") or []
    assert any(f.get("verification") == "verified" for f in findings)


def test_settings_round_trip(isolated_app):
    client, headers = isolated_app
    before = client.get("/api/settings", headers=headers)
    assert before.status_code == 200
    saved = client.put(
        "/api/settings",
        headers=headers,
        json={"username_scan_limit": 42},
    )
    assert saved.status_code == 200
    after = client.get("/api/settings", headers=headers).json()
    assert after.get("username_scan_limit") == 42


def test_intelligence_route_acquires_url_only_finding(isolated_app, monkeypatch):
    client, headers = isolated_app

    async def fake_execute(self, scan_id, profile, modules):
        return [
            Finding(
                scan_id=scan_id,
                source="web_search",
                category=FindingCategory.IDENTITY,
                platform="Web",
                title="Synthetic public result",
                url="https://public.example/profile",
                outcome=FindingOutcome.CONFIRMED,
                verification=VerificationState.VERIFIED,
            )
        ]

    acquired = []

    async def fake_acquire(url, **kwargs):
        acquired.append(url)
        return artifact_from_http(
            source_url=url,
            final_url=url,
            body="Posted by: RouteHandle99 on this public forum post.",
            status=200,
            title=kwargs["title"],
            scan_id=kwargs["scan_id"],
            budget=kwargs["budget"],
        )

    monkeypatch.setattr(ScanEngine, "_execute_modules", fake_execute)
    monkeypatch.setattr("app.services.intelligence_pipeline.acquire_page", fake_acquire)

    async def no_live_search(query: str, max_results: int):
        return []

    monkeypatch.setattr(
        "app.services.query_executor.default_web_search",
        no_live_search,
    )
    response = client.post(
        "/api/scans",
        headers=headers,
        json={
            "profile": {"username": "RouteHandle99"},
            "providers": ["web_search"],
            "async_mode": False,
        },
    )
    scan_id = response.json()["id"]
    intelligence = client.get(
        f"/api/scans/{scan_id}/intelligence?refresh=true",
        headers=headers,
    )
    assert intelligence.status_code == 200
    assert acquired == ["https://public.example/profile"]
    assert intelligence.json()["artifacts"][0]["acquisition_method"] == "http"

    active = default_budget(scan_id)
    overlapping = client.get(
        f"/api/scans/{scan_id}/intelligence?refresh=true",
        headers=headers,
    )
    assert overlapping.status_code == 409
    assert get_budget(scan_id) is active
    clear_budget(scan_id, expected=active)
