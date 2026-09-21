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


def _mark_legacy(scan_id: str, risk_score: float) -> None:
    """Simulate a pre-evidence-aware row that still needs backfill."""
    with db._connect() as conn:
        conn.execute(
            "UPDATE scans SET risk_score=?, scoring_version=0 WHERE id=?",
            (risk_score, scan_id),
        )
        conn.commit()


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
    db.update_scan_status(scan_id, "completed", finding_count=1, risk_score=12.0)
    _mark_legacy(scan_id, 12.0)

    summaries = db.list_scans(10)
    assert len(summaries) == 1
    assert abs(summaries[0].risk_score - live) < 0.05

    stored = db.get_scan(scan_id)["scan"]
    assert abs(float(stored["risk_score"]) - live) < 0.05
    assert int(stored["scoring_version"]) == db.CURRENT_SCORING_VERSION

    trends = db.risk_trends(10)
    assert len(trends) == 1
    assert abs(trends[0]["risk_score"] - live) < 0.05


def test_list_scans_skips_rescore_when_version_current(monkeypatch, tmp_path):
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
        risk_level=RiskLevel.MEDIUM,
        confidence=0.9,
        url="https://example.com/jane",
    )
    db.save_findings([finding])
    live = compute_risk_score([finding])
    db.update_scan_status(scan_id, "completed", finding_count=1, risk_score=live)

    calls = {"n": 0}
    real = compute_risk_score

    def counted(findings):
        calls["n"] += 1
        return real(findings)

    import app.services.exposure_scoring as scoring

    monkeypatch.setattr(scoring, "compute_risk_score", counted)

    first = db.list_scans(10)
    assert abs(first[0].risk_score - live) < 0.05
    assert calls["n"] == 0  # scoring_version already current

    second = db.risk_trends(10)
    assert abs(second[0]["risk_score"] - live) < 0.05
    assert calls["n"] == 0


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
    _mark_legacy(scan_id, 1.0)
    score = db.sync_risk_score(scan_id, [finding], stored=1.0)
    assert score > 50
    row = db.get_scan(scan_id)["scan"]
    assert abs(float(row["risk_score"]) - score) < 0.05
    assert int(row["scoring_version"]) == db.CURRENT_SCORING_VERSION


def test_running_scan_is_not_backfilled(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    profile = IdentityProfile(username="jane")
    scan_id = db.create_scan(profile, ["web_search"])
    # Still running with version 0 — must not stamp a partial score.
    summaries = db.list_scans(10)
    assert len(summaries) == 1
    row = db.get_scan(scan_id)["scan"]
    assert row["status"] == "running"
    assert int(row["scoring_version"]) == 0

    # Simulate completion winning the race after a concurrent backfill attempt.
    finding = Finding(
        scan_id=scan_id,
        source="web_search",
        platform="Web",
        title="Done",
        category=FindingCategory.IDENTITY,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.HIGH,
        confidence=0.9,
        url="https://example.com/jane",
    )
    db.save_findings([finding])
    live = compute_risk_score([finding])
    db.update_scan_status(scan_id, "completed", finding_count=1, risk_score=live)

    with db._connect() as conn:
        # Stale backfill must not overwrite the completion stamp.
        stale = db._backfill_scan_score(
            conn, scan_id, status="completed", stored_score=0.0
        )
        conn.commit()
    assert abs(stale - live) < 0.05
    row = db.get_scan(scan_id)["scan"]
    assert abs(float(row["risk_score"]) - live) < 0.05
    assert int(row["scoring_version"]) == db.CURRENT_SCORING_VERSION


def test_sync_skips_persist_while_running(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    profile = IdentityProfile(username="jane")
    scan_id = db.create_scan(profile, ["web_search"])
    finding = Finding(
        scan_id=scan_id,
        source="web_search",
        platform="Web",
        title="Partial",
        category=FindingCategory.IDENTITY,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.HIGH,
        confidence=0.9,
        url="https://example.com/partial",
    )
    score = db.sync_risk_score(scan_id, [finding], stored=0.0)
    assert score > 0
    row = db.get_scan(scan_id)["scan"]
    assert int(row["scoring_version"]) == 0
    assert float(row["risk_score"] or 0) == 0.0
