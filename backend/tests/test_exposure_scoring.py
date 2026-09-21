"""Evidence-aware exposure scoring tests."""

from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingCategory, FindingOutcome, RiskLevel
from app.services.exposure_scoring import compute_exposure_score, compute_risk_score


def _f(**kwargs) -> Finding:
    data = dict(
        source="web_search",
        platform="Web",
        title="Exposure",
        category=FindingCategory.IDENTITY,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.LOW,
        confidence=0.9,
        url="https://example.com/x",
    )
    data.update(kwargs)
    return Finding(**data)


def test_single_critical_not_diluted_by_many_info():
    findings = [
        _f(
            title="Password breach",
            risk_level=RiskLevel.CRITICAL,
            source="credential_leaks",
            platform="HIBP",
            url="https://hibp.example/1",
        ),
        *[_f(title=f"info-{i}", risk_level=RiskLevel.INFO, url=f"https://example.com/i{i}",
             outcome=FindingOutcome.NEGATIVE, verification=VerificationState.NOT_FOUND)
          for i in range(20)],
    ]
    score = compute_risk_score(findings)
    assert score >= 60


def test_duplicates_do_not_linearly_inflate():
    a = [
        _f(title="Same", risk_level=RiskLevel.HIGH, url="https://example.com/same"),
        _f(title="Same again", risk_level=RiskLevel.HIGH, url="https://example.com/same"),
        _f(title="Same 3", risk_level=RiskLevel.HIGH, url="https://example.com/same"),
    ]
    one = compute_risk_score([a[0]])
    many = compute_risk_score(a)
    assert abs(many - one) < 5


def test_inconclusive_and_blocked_excluded():
    findings = [
        _f(
            title="Blocked",
            risk_level=RiskLevel.HIGH,
            outcome=FindingOutcome.INCONCLUSIVE,
            verification=VerificationState.BLOCKED,
            url="https://example.com/blocked",
        ),
        _f(
            title="Possible only",
            risk_level=RiskLevel.MEDIUM,
            outcome=FindingOutcome.INCONCLUSIVE,
            verification=VerificationState.POSSIBLE,
            url="https://example.com/poss",
        ),
    ]
    result = compute_exposure_score(findings)
    assert result.score == 0.0
    assert any("Excluded" in r or "Ignored" in r or "No confirmed" in r for r in result.reasons)


def test_explanation_is_inspectable():
    findings = [
        _f(title="Critical leak", risk_level=RiskLevel.CRITICAL, url="https://a.example/1"),
        _f(
            title="Social",
            risk_level=RiskLevel.MEDIUM,
            platform="GitHub",
            url="https://github.com/jane",
            source="username_scan",
        ),
    ]
    result = compute_exposure_score(findings)
    assert result.score > 0
    assert result.contributing
    assert result.disclaimer
    assert "heuristic" in result.disclaimer.lower() or "Heuristic" in result.disclaimer


def test_derived_correlation_not_counted_as_independent_evidence():
    observed = _f(
        title="Email on public page",
        risk_level=RiskLevel.HIGH,
        platform="Web",
        url="https://example.com/profile",
        source="web_search",
    )
    derived = _f(
        title="Correlated email ↔ name",
        risk_level=RiskLevel.HIGH,
        platform="Correlation Engine",
        source="identity_correlator",
        url="",
        raw={"evidence_backed": True, "supporting_finding_ids": [observed.id or "x"]},
    )
    base = compute_risk_score([observed])
    with_derived = compute_risk_score([observed, derived])
    assert abs(with_derived - base) < 0.01
    # Platform bonus must not treat Correlation Engine as an independent source
    another = _f(
        title="GitHub",
        risk_level=RiskLevel.MEDIUM,
        platform="GitHub",
        url="https://github.com/jane",
        source="username_scan",
    )
    two_obs = compute_risk_score([observed, another])
    two_plus_derived = compute_risk_score([observed, another, derived])
    assert abs(two_plus_derived - two_obs) < 0.01
