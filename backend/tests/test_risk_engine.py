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
