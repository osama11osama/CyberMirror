"""Persistence + encryption integration."""

from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile
from app.models.evidence import VerificationState
from app.services import crypto
from app.storage import database as db


def test_encrypted_profile_round_trip(isolated_app, tmp_path, monkeypatch):
    _client, _headers = isolated_app
    profile = IdentityProfile(username="secretuser", email="secret@example.com")
    scan_id = db.create_scan(profile, ["web_search"])
    row = db.get_scan(scan_id)
    assert row is not None
    raw_profile = row["scan"]["profile_json"]
    assert "secret@example.com" not in raw_profile
    assert crypto.decrypt_text(raw_profile)
    loaded = db.profile_from_row(row["scan"])
    assert loaded.email == "secret@example.com"
    assert loaded.username == "secretuser"


def test_finding_evidence_persists_with_scan(isolated_app):
    _client, _headers = isolated_app
    scan_id = db.create_scan(IdentityProfile(username="u1"), ["username_scan"])
    f = Finding(
        scan_id=scan_id,
        source="username_scan",
        category=FindingCategory.USERNAME,
        platform="Site",
        title="Possible account: Site",
        url="https://example.com/u1",
        outcome=FindingOutcome.INCONCLUSIVE,
        verification=VerificationState.POSSIBLE,
    )
    db.save_findings([f])
    db.update_scan_status(scan_id, "completed", 1, 5)
    loaded = db.row_to_finding(db.get_scan(scan_id)["findings"][0])
    assert loaded.verification == VerificationState.POSSIBLE
