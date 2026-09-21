"""Evidence / provenance serialization and persistence."""

from app.models.evidence import EvidenceKind, EvidenceObservation, VerificationState
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile
from app.storage import database as db


def test_evidence_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(db.settings, "database_path", tmp_path / "ev.sqlite3")
    monkeypatch.setattr(db.settings, "encryption_enabled", False)
    db.init_db()

    evidence = EvidenceObservation(
        kind=EvidenceKind.OBSERVATION,
        method="http",
        queried_identifier="janedoe",
        identifier_type="username",
        source_url="https://example.com/janedoe",
        platform="Example",
        http_status=200,
        positive_markers=["@janedoe"],
        confidence_reason="marker match",
        verification=VerificationState.VERIFIED,
    )
    finding = Finding(
        scan_id="s1",
        source="username_scan",
        category=FindingCategory.USERNAME,
        platform="Example",
        title="Account verified: Example",
        url="https://example.com/janedoe",
        confidence=0.92,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        evidence=evidence,
    )
    scan_id = db.create_scan(IdentityProfile(username="janedoe"), ["username_scan"])
    finding.scan_id = scan_id
    db.save_findings([finding])
    db.update_scan_status(scan_id, "completed", finding_count=1)

    loaded = db.get_scan(scan_id)
    assert loaded is not None
    restored = db.row_to_finding(loaded["findings"][0])
    assert restored.verification == VerificationState.VERIFIED
    assert restored.evidence is not None
    assert restored.evidence.method == "http"
    assert restored.evidence.positive_markers == ["@janedoe"]
    assert restored.raw.get("verification") == "verified"
