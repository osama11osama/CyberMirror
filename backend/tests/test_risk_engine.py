"""Tests for risk engine."""

from app.models.schemas import Finding, FindingCategory, IdentityProfile, RiskLevel
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
    )
    analyze_finding(f, IdentityProfile(email="jane@example.com"))
    assert f.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def test_ahmia_high_confidence_is_high_risk():
    f = Finding(
        source="ahmia_search", platform="Ahmia", title="Onion mention",
        category=FindingCategory.ADVANCED, confidence=0.8,
    )
    analyze_finding(f, IdentityProfile(username="jane"))
    assert f.risk_level == RiskLevel.HIGH
