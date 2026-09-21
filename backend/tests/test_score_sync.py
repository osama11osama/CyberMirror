"""Legacy risk_score recomputation stays consistent across read paths."""

from app.config import settings
from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile, RiskLevel
from app.services.exposure_scoring import compute_risk_score
from app.storage import database as db


def _prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_path", tmp_path / "score-sync.sqlite3")
    monkeypatch.setattr(settings, "encryption_enabled", False)
    db.init_db()


def test_list_scans_and_trends_recompute_legacy_scores(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    profile = IdentityProfile(username="jane")
    scan_id = db.create_scan(profile, ["web_search"])
    finding = Finding(
        scan_id=scan_id,
        source="web_search",
        platform="Web",
        title="Public profile",
        category=FindingCategory.IDENTITY,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.HIGH,
        confidence=0.9,
        url="https://example.com/jane",
    )
    db.save_findings([finding])
    live = compute_risk_score([finding])
    # Simulate a pre-v2.4 arithmetic-mean row.
    db.update_scan_status(scan_id, "completed", finding_count=1, risk_score=12.0)

    summaries = db.list_scans(10)
    assert len(summaries) == 1
    assert abs(summaries[0].risk_score - live) < 0.05

    trends = db.risk_trends(10)
    assert len(trends) == 1
    assert abs(trends[0]["risk_score"] - live) < 0.05

    # Persisted for subsequent cheap reads
    stored = db.get_scan(scan_id)["scan"]["risk_score"]
    assert abs(float(stored) - live) < 0.05


def test_sync_risk_score_updates_storage(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    profile = IdentityProfile(username="jane")
    scan_id = db.create_scan(profile, ["web_search"])
    finding = Finding(
        scan_id=scan_id,
        source="credential_leaks",
        platform="HIBP",
        title="Breach",
        category=FindingCategory.ADVANCED,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.CRITICAL,
        confidence=0.95,
        url="https://hibp.example/1",
    )
    db.save_findings([finding])
    db.update_scan_status(scan_id, "completed", finding_count=1, risk_score=1.0)
    score = db.sync_risk_score(scan_id, [finding], stored=1.0)
    assert score > 50
    assert abs(float(db.get_scan(scan_id)["scan"]["risk_score"]) - score) < 0.05
