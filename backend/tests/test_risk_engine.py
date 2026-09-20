"""Tests for risk engine."""

from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile, RiskLevel
from app.services.risk_engine import analyze_finding, compute_risk_score


def test_phone_exposure_high_risk():
    f = Finding(
        source="web_search", platform="Web", title="Phone listing",
        url="https://example.com", category=FindingCategory.IDENTITY,
        snippet="call Jane +1234567890",
    )
    profile = IdentityProfile(phone="+1234567890", full_name="Jane")
    analyze_finding(f, profile)
    assert f.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL, RiskLevel.MEDIUM)


def test_risk_score_empty():
    assert compute_risk_score([]) == 0.0


def test_credential_leak_is_high_or_critical():
    f = Finding(
        source="credential_leaks", platform="HIBP", title="Email in breach",
        category=FindingCategory.EMAIL, snippet="password hash exposed",
        outcome=FindingOutcome.CONFIRMED,
    )
    analyze_finding(f, IdentityProfile(email="jane@example.com"))
    assert f.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert f.outcome == FindingOutcome.CONFIRMED


def test_ahmia_high_confidence_is_high_risk():
    f = Finding(
        source="ahmia_search", platform="Ahmia", title="Onion mention",
        category=FindingCategory.ADVANCED, confidence=0.8,
    )
    analyze_finding(f, IdentityProfile(username="jane"))
    assert f.risk_level == RiskLevel.HIGH


def test_no_known_breaches_is_not_high_risk():
    f = Finding(
        source="breach_scan", platform="HIBP",
        title="No known breaches for jane@example.com",
        category=FindingCategory.EMAIL, confidence=0.92,
        outcome=FindingOutcome.NEGATIVE,
    )
    analyze_finding(f, IdentityProfile(email="jane@example.com"))
    assert f.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert f.risk_level == RiskLevel.INFO
    assert f.outcome == FindingOutcome.NEGATIVE


def test_inconclusive_breach_is_not_confirmed_exposure():
    f = Finding(
        source="breach_scan", platform="HIBP",
        title="Breach check inconclusive",
        category=FindingCategory.EMAIL, confidence=0.35,
        outcome=FindingOutcome.INCONCLUSIVE,
    )
    analyze_finding(f, IdentityProfile(email="jane@example.com"))
    assert f.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert f.outcome == FindingOutcome.INCONCLUSIVE


def test_system_finding_is_info():
    f = Finding(
        source="credential_leaks", platform="System",
        title="No email provided",
        category=FindingCategory.EMAIL,
        outcome=FindingOutcome.SYSTEM,
    )
    analyze_finding(f, IdentityProfile())
    assert f.risk_level == RiskLevel.INFO
    assert f.outcome == FindingOutcome.SYSTEM


def test_registration_signal_is_medium_not_breach_critical():
    f = Finding(
        source="email_scan", platform="Spotify",
        title="Email registered on Spotify",
        category=FindingCategory.EMAIL, confidence=0.75,
    )
    analyze_finding(f, IdentityProfile(email="jane@example.com"))
    assert f.risk_level == RiskLevel.MEDIUM
    assert f.outcome == FindingOutcome.CONFIRMED


def test_ahmia_negative_status_is_not_high_risk():
    f = Finding(
        source="ahmia_search", platform="Ahmia",
        title="No Tor index matches found",
        category=FindingCategory.ADVANCED, confidence=0.7,
        outcome=FindingOutcome.NEGATIVE,
        description="Rotate passwords periodically and enable MFA.",
    )
    analyze_finding(f, IdentityProfile(username="jane"))
    assert f.risk_level == RiskLevel.INFO
    assert f.outcome == FindingOutcome.NEGATIVE


def test_negative_credential_advice_with_password_word_is_not_critical():
    f = Finding(
        source="credential_leaks", platform="HIBP",
        title="No credential leaks found for jane@example.com",
        category=FindingCategory.EMAIL, confidence=0.92,
        outcome=FindingOutcome.NEGATIVE,
        description="Rotate passwords periodically and enable MFA.",
    )
    analyze_finding(f, IdentityProfile(email="jane@example.com"))
    assert f.risk_level == RiskLevel.INFO
    assert f.risk_level != RiskLevel.CRITICAL
