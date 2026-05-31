"""Native email exposure scanner — checks public registration signals."""

import logging

import httpx

from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.modules.identity.web_search import WebSearchModule

logger = logging.getLogger(__name__)


class EmailScanModule(NativeModule):
    id = "email_scan"
    name = "CyberMirror Email Scanner"
    description = "Detects public email exposure via web search and registration signals"
    category = "email_exposure"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        email = profile.email.strip()
        if not email or "@" not in email:
            return []

        findings: list[Finding] = []

        # Web search for email in public results
        search = WebSearchModule(max_queries=3, results_per_query=5)
        mini = IdentityProfile(email=email, full_name=profile.full_name, phone=profile.phone)
        for hit in await search.scan(mini, scan_id):
            combined = f"{hit.title} {hit.snippet} {hit.url}".lower()
            if email.lower() in combined:
                findings.append(Finding(
                    scan_id=scan_id,
                    source=self.id,
                    provider="EmailScanModule",
                    category=FindingCategory.EMAIL,
                    platform="Web",
                    title="Email exposed in public web result",
                    url=hit.url,
                    snippet=hit.snippet,
                    description=f"Found via query: {hit.description}",
                    confidence=0.88,
                ))

        # Gravatar public profile check (email hash not needed — username-style)
        local = email.split("@")[0]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://en.gravatar.com/{local}")
                if resp.status_code == 200 and "404" not in resp.text[:2000].lower():
                    findings.append(Finding(
                        scan_id=scan_id,
                        source=self.id,
                        provider="EmailScanModule",
                        category=FindingCategory.EMAIL,
                        platform="Gravatar",
                        title="Possible Gravatar profile linked to email prefix",
                        url=f"https://en.gravatar.com/{local}",
                        confidence=0.6,
                        description="Public avatar/profile may reveal identity",
                    ))
        except Exception as exc:
            logger.debug("Gravatar check failed: %s", exc)

        return findings
