"""Risk scoring engine."""

from app.models.schemas import Finding, FindingOutcome, IdentityProfile, RiskLevel

RISK_WEIGHTS = {
    RiskLevel.CRITICAL: 100,
    RiskLevel.HIGH: 75,
    RiskLevel.MEDIUM: 50,
    RiskLevel.LOW: 25,
    RiskLevel.INFO: 10,
    RiskLevel.UNKNOWN: 0,
}

SOCIAL_DOMAINS = (
    "github.com", "linkedin.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "tiktok.com", "reddit.com",
)

_NEGATIVE_TITLE_MARKERS = (
    "no known breaches",
    "no credential leaks found",
    "no breaches found",
)
_INCONCLUSIVE_TITLE_MARKERS = (
    "inconclusive",
)
_SYSTEM_TITLE_MARKERS = (
    "no email provided",
)


def _contains(text: str, needle: str) -> bool:
    return bool(needle and needle.lower() in text.lower())


def _resolve_outcome(finding: Finding) -> FindingOutcome:
    if finding.outcome and finding.outcome != FindingOutcome.UNKNOWN:
        return finding.outcome
    raw_outcome = (finding.raw or {}).get("outcome")
    if isinstance(raw_outcome, str):
        try:
            return FindingOutcome(raw_outcome)
        except ValueError:
            pass
    title = (finding.title or "").lower()
    if any(m in title for m in _SYSTEM_TITLE_MARKERS):
        return FindingOutcome.SYSTEM
    if any(m in title for m in _NEGATIVE_TITLE_MARKERS):
        return FindingOutcome.NEGATIVE
    if any(m in title for m in _INCONCLUSIVE_TITLE_MARKERS):
        return FindingOutcome.INCONCLUSIVE
    return FindingOutcome.UNKNOWN


def analyze_finding(finding: Finding, profile: IdentityProfile) -> Finding:
    combined = f"{finding.title} {finding.description} {finding.snippet} {finding.url}"
    outcome = _resolve_outcome(finding)
    finding.outcome = outcome

    if outcome == FindingOutcome.SYSTEM:
        finding.risk_level = RiskLevel.INFO
        finding.risk_reason = "System or status message — not public exposure"
        finding.recommendation = "Provide the missing input if you want this check to run"
        return finding

    if outcome == FindingOutcome.NEGATIVE:
        finding.risk_level = RiskLevel.INFO
        finding.risk_reason = "No confirmed exposure found for this check"
        finding.recommendation = "Keep rotating passwords periodically and enable MFA"
        return finding

    if outcome == FindingOutcome.INCONCLUSIVE:
        finding.risk_level = RiskLevel.LOW
        finding.risk_reason = "Check was inconclusive — not confirmed exposure"
        finding.recommendation = "Add an API key or re-run with more complete inputs for certainty"
        return finding

    has_name = _contains(combined, profile.full_name)
    has_email = _contains(combined, profile.email)
    has_phone = _contains(combined, profile.phone)
    has_username = _contains(combined, profile.username)
    has_location = _contains(combined, profile.location)
    is_social = any(d in finding.url.lower() for d in SOCIAL_DOMAINS)
    is_registration = (
        finding.source == "email_scan"
        and "registered on" in (finding.title or "").lower()
    )

    if has_phone and has_name and has_location:
        finding.risk_level = RiskLevel.CRITICAL
        finding.risk_reason = "Phone, name, and location appear together publicly"
        finding.recommendation = "Remove public phone listings; request data broker removal"
    elif has_email and (has_name or has_phone):
        finding.risk_level = RiskLevel.HIGH
        finding.risk_reason = "Email linked to real identity in public result"
        finding.recommendation = "Use alias email publicly; enable MFA on affected accounts"
    elif has_phone and has_name:
        finding.risk_level = RiskLevel.HIGH
        finding.risk_reason = "Phone number and name exposed together"
        finding.recommendation = "Remove phone from public profiles and directories"
    elif finding.platform.startswith("HIBP") or finding.source == "credential_leaks":
        finding.outcome = FindingOutcome.CONFIRMED
        finding.risk_level = RiskLevel.CRITICAL if "password" in combined.lower() else RiskLevel.HIGH
        finding.risk_reason = "Credential or breach exposure detected"
        finding.recommendation = "Change passwords immediately; enable MFA; check for unauthorized account access"
    elif finding.source == "ahmia_search" and finding.confidence >= 0.6:
        finding.risk_level = RiskLevel.HIGH
        finding.risk_reason = "Identity term found in Tor hidden-service index"
        finding.recommendation = "Verify the match manually; rotate credentials if confirmed; avoid visiting unknown .onion links"
    elif finding.source == "ahmia_search":
        finding.risk_level = RiskLevel.MEDIUM
        finding.risk_reason = "Possible Tor index mention (lower confidence)"
        finding.recommendation = "Review manually — may be a generic or unrelated index hit"
    elif is_registration:
        finding.outcome = FindingOutcome.CONFIRMED
        finding.risk_level = RiskLevel.MEDIUM
        finding.risk_reason = "Registration signal — email may be enrolled on a public service"
        finding.recommendation = "Review account privacy; delete unused registrations"
    elif finding.category.value == "email_exposure":
        finding.outcome = FindingOutcome.CONFIRMED
        finding.risk_level = RiskLevel.HIGH
        finding.risk_reason = "Email registered on a public-facing service"
        finding.recommendation = "Review account privacy; delete unused registrations"
    elif is_social and (has_name or has_username):
        finding.risk_level = RiskLevel.MEDIUM
        finding.risk_reason = "Social profile connected to identity"
        finding.recommendation = "Tighten social media privacy settings"
    elif has_username and has_location:
        finding.risk_level = RiskLevel.MEDIUM
        finding.risk_reason = "Username and location appear together"
        finding.recommendation = "Use unique usernames per platform"
    elif has_name or has_username:
        finding.risk_level = RiskLevel.LOW
        finding.risk_reason = "Generic identity marker detected"
        finding.recommendation = "Monitor periodically for new exposure"
    elif finding.confidence > 0:
        finding.risk_level = RiskLevel.INFO
        finding.risk_reason = "Informational finding"
        finding.recommendation = "Review and archive if no action needed"
    else:
        finding.risk_level = RiskLevel.UNKNOWN
        finding.risk_reason = "Insufficient context for risk assessment"
        finding.recommendation = "Manual review recommended"

    return finding


def compute_risk_score(findings: list[Finding]) -> float:
    if not findings:
        return 0.0
    total = sum(RISK_WEIGHTS.get(f.risk_level, 0) for f in findings)
    return round(min(100.0, total / len(findings)), 1)
