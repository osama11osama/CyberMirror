"""Breach exposure check — HIBP API (optional key) + web search fallback."""

import asyncio
import hashlib
import logging

import httpx

from app.config import settings
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule

logger = logging.getLogger(__name__)


class BreachScanModule(NativeModule):
    id = "breach_scan"
    name = "CyberMirror Breach Scanner"
    description = "Check if email appears in known data breaches (HIBP)"
    category = "email_exposure"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        email = profile.email.strip().lower()
        if not email:
            return []

        findings: list[Finding] = []

        if settings.hibp_api_key:
            findings.extend(await self._hibp_api(email, scan_id))

        if not findings:
            findings.extend(await self._web_fallback(email, scan_id))

        if not findings:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="BreachScanModule",
                category=FindingCategory.EMAIL, platform="HIBP",
                title=f"No known breaches for {email}",
                description="No public breach records found (or HIBP API key not set).",
                confidence=0.5,
            ))

        return findings

    async def _hibp_api(self, email: str, scan_id: str) -> list[Finding]:
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
        headers = {
            "hibp-api-key": settings.hibp_api_key,
            "User-Agent": "CyberMirror-SelfAudit",
        }
        findings: list[Finding] = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers=headers, params={"truncateResponse": "false"})
            if resp.status_code == 404:
                return findings
            if resp.status_code != 200:
                logger.warning("HIBP API status %s", resp.status_code)
                return findings
            for breach in resp.json():
                findings.append(Finding(
                    scan_id=scan_id, source=self.id, provider="BreachScanModule",
                    category=FindingCategory.EMAIL, platform="HIBP",
                    title=f"Breached: {breach.get('Name', 'Unknown')}",
                    url=f"https://haveibeenpwned.com/account/{email}",
                    description=breach.get("Description", "")[:400],
                    snippet=f"Date: {breach.get('BreachDate', '?')} · {breach.get('DataClasses', [])}",
                    confidence=0.95,
                    raw=breach,
                ))
        except Exception as exc:
            logger.warning("HIBP API error: %s", exc)
        return findings

    async def _web_fallback(self, email: str, scan_id: str) -> list[Finding]:
        try:
            from ddgs import DDGS
        except ImportError:
            return []

        findings: list[Finding] = []
        query = f'site:haveibeenpwned.com "{email}"'
        try:
            with DDGS(timeout=20) as ddgs:
                results = await asyncio.to_thread(
                    lambda: list(ddgs.text(query, max_results=5))
                )
            for item in results:
                findings.append(Finding(
                    scan_id=scan_id, source=self.id, provider="BreachScanModule",
                    category=FindingCategory.EMAIL, platform="HIBP",
                    title=item.get("title") or "Possible breach mention",
                    url=item.get("href") or item.get("link") or "",
                    description=f"Web search: {query}",
                    snippet=(item.get("body") or "")[:300],
                    confidence=0.6,
                ))
        except Exception as exc:
            logger.warning("Breach web search failed: %s", exc)
        return findings
