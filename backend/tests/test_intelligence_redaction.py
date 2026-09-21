"""Persisted intelligence artifact redaction (#53 Codex)."""

from app.config import settings
from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile, RiskLevel
from app.services.intelligence_pipeline import analyze_finding_pages
from app.storage import database as db


def test_redact_intelligence_artifacts_clears_main_text(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "intel.sqlite3")
    monkeypatch.setattr(settings, "encryption_enabled", False)
    db.init_db()
    profile = IdentityProfile(username="jane")
    scan_id = db.create_scan(profile, ["web_search"])
    finding = Finding(
        scan_id=scan_id,
        source="web_search",
        platform="Web",
        title="Review",
        url="https://example.com/r",
        category=FindingCategory.IDENTITY,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.LOW,
        raw={"page_text": "Posted by: jane\nStayed June 2026 in Lisbon. Secret body text."},
    )
    db.save_findings([finding])
    payload = analyze_finding_pages(profile, [finding], scan_id=scan_id)
    db.save_intelligence(scan_id, payload)
    assert any((a.get("main_text") or "") for a in payload.get("artifacts") or [])

    n = db.redact_intelligence_artifacts(scan_id)
    assert n >= 1
    loaded = db.load_intelligence(scan_id)
    assert loaded
    for art in loaded.get("artifacts") or []:
        assert art.get("main_text") == ""
        assert art.get("content_redacted") is True


def test_redact_persists_metadata_only_artifacts(tmp_path, monkeypatch):
    """Artifacts with empty main_text but metadata.body must still be saved."""
    monkeypatch.setattr(settings, "database_path", tmp_path / "intel-meta.sqlite3")
    monkeypatch.setattr(settings, "encryption_enabled", False)
    db.init_db()
    profile = IdentityProfile(username="jane")
    scan_id = db.create_scan(profile, ["web_search"])
    db.update_scan_status(scan_id, "completed", finding_count=0, risk_score=0.0)
    db.save_intelligence(
        scan_id,
        {
            "artifacts": [
                {
                    "id": "a1",
                    "main_text": "",
                    "metadata": {"raw_html": "<html>secret</html>", "body": "secret body"},
                }
            ]
        },
    )
    n = db.redact_intelligence_artifacts(scan_id)
    assert n == 1
    loaded = db.load_intelligence(scan_id)
    assert loaded is not None
    art = loaded["artifacts"][0]
    assert "raw_html" not in (art.get("metadata") or {})
    assert "body" not in (art.get("metadata") or {})
    assert art.get("content_redacted") is True
