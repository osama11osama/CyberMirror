"""Cross-platform identity correlation — links findings across platforms."""

import re
from collections import defaultdict
from urllib.parse import urlparse

from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile
from app.models.evidence import (
    EvidenceKind,
    EvidenceObservation,
    VerificationState,
)
from app.modules.base import NativeModule


class IdentityCorrelatorModule(NativeModule):
    id = "identity_correlator"
    name = "CyberMirror Identity Correlator"
    description = "Correlates findings across platforms and profile fields"
    category = "identity_search"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        # Standalone module run has no observed findings yet — seed fields alone are not evidence.
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


def _blob(finding: Finding) -> str:
    """Observed evidence only — skip description (often embeds search-query seeds)."""
    return f"{finding.title} {finding.snippet} {finding.url}".lower()


def _mentions(finding: Finding, *needles: str) -> bool:
    text = _blob(finding)
    return all(n and n.lower() in text for n in needles)


def _supporting(existing: list[Finding], *needles: str) -> list[Finding]:
    return [f for f in existing if _mentions(f, *needles)]


def correlate_findings(
    profile: IdentityProfile,
    existing: list[Finding],
    scan_id: str = "",
) -> list[Finding]:
    """Build correlations from observed findings only — never from seed inputs alone."""
    findings: list[Finding] = []
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
        if profile.username and profile.username.lower() in _blob(f):
            handle_platforms[profile.username.lower()].add(f.platform)

    # Evidence-backed seed-field pairs: only when a public finding links both values.
    if profile.full_name and profile.username:
        support = _supporting(existing, profile.full_name, profile.username)
        if support:
            findings.append(_corr(
                scan_id,
                "Name + Username linked in public results",
                "Observed sources mention both the real name and username together.",
                support,
                pair=(profile.full_name, profile.username),
            ))

    if profile.email and profile.full_name:
        support = _supporting(existing, profile.email, profile.full_name)
        if support:
            findings.append(_corr(
                scan_id,
                "Email + Real Name linked in public results",
                "Observed sources mention both the email and real name together.",
                support,
                pair=(profile.email, profile.full_name),
            ))

    if profile.phone and profile.location:
        support = _supporting(existing, profile.phone, profile.location)
        if support:
            findings.append(_corr(
                scan_id,
                "Phone + Location linked in public results",
                "Observed sources mention both the phone and location together.",
                support,
                pair=(profile.phone, profile.location),
            ))

    real_platforms = list(by_platform.keys())
    if len(real_platforms) >= 5:
        support = [f for plats in by_platform.values() for f in plats]
        findings.append(Finding(
            scan_id=scan_id,
            source="identity_correlator",
            provider="IdentityCorrelatorModule",
            category=FindingCategory.IDENTITY,
            platform="Correlation Engine",
            title=f"Username found on {len(real_platforms)} platforms",
            description=f"Platforms: {', '.join(sorted(real_platforms)[:15])}",
            confidence=0.9,
            outcome=FindingOutcome.CONFIRMED,
            raw={
                "outcome": FindingOutcome.CONFIRMED.value,
                "supporting_finding_ids": [f.id for f in support[:50]],
                "platforms": sorted(real_platforms),
            },
        ))

    for handle, platforms in handle_platforms.items():
        if len(platforms) >= 3 and handle != "www":
            support = [
                f for f in existing
                if _extract_handle(f.url) == handle
                or (profile.username and profile.username.lower() == handle and handle in _blob(f))
            ]
            findings.append(Finding(
                scan_id=scan_id,
                source="identity_correlator",
                provider="IdentityCorrelatorModule",
                category=FindingCategory.IDENTITY,
                platform="Correlation Engine",
                title=f"Handle '{handle}' linked across {len(platforms)} platforms",
                description=f"Same URL handle on: {', '.join(sorted(platforms)[:10])}",
                confidence=0.87,
                outcome=FindingOutcome.CONFIRMED,
                raw={
                    "outcome": FindingOutcome.CONFIRMED.value,
                    "supporting_finding_ids": [f.id for f in support[:50]],
                    "platforms": sorted(platforms),
                },
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
            outcome=FindingOutcome.CONFIRMED,
            raw={
                "outcome": FindingOutcome.CONFIRMED.value,
                "supporting_finding_ids": [f.id for f in high[:50]],
            },
        ))

    if profile.email:
        email_hits = [
            f for f in existing
            if profile.email.lower() in _blob(f)
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
                outcome=FindingOutcome.CONFIRMED,
                raw={
                    "outcome": FindingOutcome.CONFIRMED.value,
                    "supporting_finding_ids": [f.id for f in email_hits[:50]],
                },
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
                outcome=FindingOutcome.CONFIRMED,
                raw={
                    "outcome": FindingOutcome.CONFIRMED.value,
                    "supporting_finding_ids": [f.id for f in title_matches[:50]],
                },
            ))

    return findings


def _corr(
    scan_id: str,
    title: str,
    desc: str,
    support: list[Finding],
    *,
    pair: tuple[str, ...] = (),
) -> Finding:
    sources = sorted({f.source or f.platform for f in support if f.source or f.platform})
    # Snippet carries only the correlated pair — never extra seed fields (e.g. location).
    snippet = " | ".join(part for part in pair if part)
    support_ids = [f.id for f in support[:50]]
    evidence = EvidenceObservation(
        kind=EvidenceKind.DERIVED,
        method="correlator",
        queried_identifier=" | ".join(pair),
        identifier_type="correlated_pair",
        platform="Correlation Engine",
        positive_markers=[s for s in sources[:8]],
        confidence_reason="Multiple observed findings mention both identifiers",
        corroborating_finding_ids=support_ids,
        verification=VerificationState.LIKELY,
    )
    return Finding(
        scan_id=scan_id,
        source="identity_correlator",
        provider="IdentityCorrelatorModule",
        category=FindingCategory.IDENTITY,
        platform="Correlation Engine",
        title=title,
        description=f"{desc} Supporting sources: {', '.join(sources[:8]) or 'observed findings'}.",
        confidence=0.9,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.LIKELY,
        evidence=evidence,
        snippet=snippet,
        raw={
            "outcome": FindingOutcome.CONFIRMED.value,
            "verification": VerificationState.LIKELY.value,
            "supporting_finding_ids": support_ids,
            "supporting_sources": sources[:20],
            "evidence_backed": True,
        },
    )
