"""Cross-platform identity correlation — links findings to build a dossier."""

from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule


class IdentityCorrelatorModule(NativeModule):
    id = "identity_correlator"
    name = "CyberMirror Identity Correlator"
    description = "Correlates username, email, name and location across all findings"
    category = "identity_search"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        """Generates correlation insights from profile fields (runs after other modules)."""
        findings: list[Finding] = []
        markers = []

        if profile.full_name and profile.username:
            markers.append(("Name + Username linked", "Using same identity across platforms increases traceability"))
        if profile.email and profile.full_name:
            markers.append(("Email + Real Name", "High risk — email and name publicly associated"))
        if profile.phone and profile.location:
            markers.append(("Phone + Location", "Critical — enables physical-world identification"))
        if profile.username and profile.location:
            markers.append(("Username + Location", "Medium risk — geo-locatable online presence"))

        for title, desc in markers:
            findings.append(Finding(
                scan_id=scan_id,
                source=self.id,
                provider="IdentityCorrelatorModule",
                category=FindingCategory.IDENTITY,
                platform="Correlation Engine",
                title=title,
                description=desc,
                confidence=0.95,
                snippet=f"Profile: {profile.full_name or 'N/A'} | {profile.username or 'N/A'} | {profile.location or 'N/A'}",
            ))
        return findings
