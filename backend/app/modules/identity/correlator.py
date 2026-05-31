"""Cross-platform identity correlation — links findings across platforms."""

import re
from collections import defaultdict
from urllib.parse import urlparse

from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule


class IdentityCorrelatorModule(NativeModule):
    id = "identity_correlator"
    name = "CyberMirror Identity Correlator"
    description = "Correlates findings across platforms and profile fields"
    category = "identity_search"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        return correlate_findings(profile, [], scan_id)


def _extract_handle(url: str) -> str | None:
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    parts = path.split("/")
    for skip in ("in", "u", "user", "profile.php"):
        if parts and parts[0] == skip:
            parts = parts[1:]
    handle = parts[0].lstrip("@") if parts else None
    if handle and len(handle) >= 2 and handle not in ("search", "watch", "p"):
        return handle.lower()
    return None


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
    handle_platforms: dict[str, set[str]] = defaultdict(set)

    for f in existing:
        if f.platform in ("Summary", "System", "Correlation Engine"):
            continue
        by_platform[f.platform].append(f)
        handle = _extract_handle(f.url)
        if handle:
            handle_platforms[handle].add(f.platform)
        if profile.username and profile.username.lower() in f"{f.title} {f.url} {f.snippet}".lower():
            handle_platforms[profile.username.lower()].add(f.platform)

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

    for handle, platforms in handle_platforms.items():
        if len(platforms) >= 3 and handle != "www":
            findings.append(Finding(
                scan_id=scan_id,
                source="identity_correlator",
                provider="IdentityCorrelatorModule",
                category=FindingCategory.IDENTITY,
                platform="Correlation Engine",
                title=f"Handle '{handle}' linked across {len(platforms)} platforms",
                description=f"Same URL handle on: {', '.join(sorted(platforms)[:10])}",
                confidence=0.87,
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

    if profile.username:
        uname = re.escape(profile.username.lower())
        title_matches = [
            f for f in existing
            if re.search(rf"\b{uname}\b", f"{f.title} {f.snippet}".lower())
        ]
        if len(title_matches) >= 4:
            findings.append(Finding(
                scan_id=scan_id,
                source="identity_correlator",
                provider="IdentityCorrelatorModule",
                category=FindingCategory.USERNAME,
                platform="Correlation Engine",
                title=f"Username '{profile.username}' repeated in {len(title_matches)} findings",
                description="Consistent username reuse increases traceability",
                confidence=0.85,
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
