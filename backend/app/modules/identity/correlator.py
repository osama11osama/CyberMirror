"""Cross-platform identity correlation — links findings across platforms."""

from collections import defaultdict

from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule


class IdentityCorrelatorModule(NativeModule):
    id = "identity_correlator"
    name = "CyberMirror Identity Correlator"
    description = "Correlates findings across platforms and profile fields"
    category = "identity_search"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        return correlate_findings(profile, [], scan_id)


def correlate_findings(
    profile: IdentityProfile,
    existing: list[Finding],
    scan_id: str = "",
) -> list[Finding]:
    findings: list[Finding] = []

    if profile.full_name and profile.username:
        findings.append(_corr(
            scan_id, "Name + Username linked",
            "Same identity used across platforms — easier to trace",
            profile,
        ))
    if profile.email and profile.full_name:
        findings.append(_corr(
            scan_id, "Email + Real Name exposed",
            "High risk — real identity tied to email in public results",
            profile,
        ))
    if profile.phone and profile.location:
        findings.append(_corr(
            scan_id, "Phone + Location exposed",
            "Critical — enables physical-world identification",
            profile,
        ))

    if not existing:
        return findings

    by_platform: dict[str, list[Finding]] = defaultdict(list)
    for f in existing:
        if f.platform not in ("Summary", "System", "Correlation Engine"):
            by_platform[f.platform].append(f)

    real_platforms = list(by_platform.keys())
    if len(real_platforms) >= 5:
        findings.append(Finding(
            scan_id=scan_id,
            source="identity_correlator",
            provider="IdentityCorrelatorModule",
            category=FindingCategory.IDENTITY,
            platform="Correlation Engine",
            title=f"Username found on {len(real_platforms)} platforms",
            description=f"Platforms: {', '.join(sorted(real_platforms)[:15])}",
            confidence=0.9,
        ))

    high = [f for f in existing if f.risk_level.value in ("Critical", "High")]
    if len(high) >= 3:
        findings.append(Finding(
            scan_id=scan_id,
            source="identity_correlator",
            provider="IdentityCorrelatorModule",
            category=FindingCategory.IDENTITY,
            platform="Correlation Engine",
            title=f"{len(high)} high-risk exposures detected",
            description="Multiple sensitive data points found publicly",
            confidence=0.95,
        ))

    if profile.email:
        email_hits = [
            f for f in existing
            if profile.email.lower() in f"{f.title} {f.snippet} {f.url}".lower()
        ]
        if len(email_hits) >= 2:
            findings.append(Finding(
                scan_id=scan_id,
                source="identity_correlator",
                provider="IdentityCorrelatorModule",
                category=FindingCategory.EMAIL,
                platform="Correlation Engine",
                title=f"Email appears in {len(email_hits)} public results",
                description="Email widely indexed — consider alias addresses publicly",
                confidence=0.88,
            ))

    return findings


def _corr(scan_id: str, title: str, desc: str, profile: IdentityProfile) -> Finding:
    return Finding(
        scan_id=scan_id,
        source="identity_correlator",
        provider="IdentityCorrelatorModule",
        category=FindingCategory.IDENTITY,
        platform="Correlation Engine",
        title=title,
        description=desc,
        confidence=0.95,
        snippet=f"{profile.full_name or ''} | {profile.username or ''} | {profile.location or ''}".strip(),
    )
