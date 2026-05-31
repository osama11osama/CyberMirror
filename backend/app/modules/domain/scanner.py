"""Domain / website OSINT — WHOIS and public web mentions."""

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx

from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule

logger = logging.getLogger(__name__)


class DomainScanModule(NativeModule):
    id = "domain_scan"
    name = "CyberMirror Domain Scanner"
    description = "WHOIS lookup and web search for personal websites"
    category = "identity_search"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        website = profile.website.strip()
        if not website:
            return []

        if not website.startswith("http"):
            website = f"https://{website}"

        domain = urlparse(website).netloc.replace("www.", "")
        if not domain:
            return []

        findings: list[Finding] = []

        whois_text = await self._whois(domain)
        if whois_text:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="DomainScanModule",
                category=FindingCategory.IDENTITY, platform="WHOIS",
                title=f"WHOIS: {domain}",
                url=website,
                description="Domain registration data (public WHOIS)",
                snippet=whois_text[:600],
                confidence=0.85,
                raw={"domain": domain},
            ))

        findings.extend(await self._web_mentions(domain, profile, scan_id))
        return findings

    async def _whois(self, domain: str) -> str:
        try:
            import whois
            data = await asyncio.to_thread(whois.whois, domain)
            parts = []
            for key in ("domain_name", "registrar", "creation_date", "expiration_date", "name", "org", "emails"):
                val = getattr(data, key, None) if hasattr(data, key) else data.get(key) if isinstance(data, dict) else None
                if val:
                    parts.append(f"{key}: {val}")
            return "\n".join(parts) if parts else str(data)[:600]
        except ImportError:
            return await self._whois_web(domain)
        except Exception as exc:
            logger.debug("WHOIS failed for %s: %s", domain, exc)
            return await self._whois_web(domain)

    async def _whois_web(self, domain: str) -> str:
        try:
            from ddgs import DDGS
            with DDGS(timeout=15) as ddgs:
                results = await asyncio.to_thread(
                    lambda: list(ddgs.text(f"whois {domain}", max_results=3))
                )
            return " · ".join(r.get("body", "")[:200] for r in results)
        except Exception:
            return ""

    async def _web_mentions(self, domain: str, profile: IdentityProfile, scan_id: str) -> list[Finding]:
        try:
            from ddgs import DDGS
        except ImportError:
            return []

        name = profile.full_name or profile.username
        query = f'site:{domain} {name}'.strip() if name else f"site:{domain}"
        findings: list[Finding] = []
        try:
            with DDGS(timeout=20) as ddgs:
                results = await asyncio.to_thread(
                    lambda: list(ddgs.text(query, max_results=5))
                )
            for item in results:
                findings.append(Finding(
                    scan_id=scan_id, source=self.id, provider="DomainScanModule",
                    category=FindingCategory.IDENTITY, platform=domain,
                    title=item.get("title") or "Site page",
                    url=item.get("href") or item.get("link") or website_fix(domain),
                    description=f"Indexed page on {domain}",
                    snippet=(item.get("body") or "")[:300],
                    confidence=0.7,
                ))
        except Exception as exc:
            logger.warning("Domain web search failed: %s", exc)
        return findings


def website_fix(domain: str) -> str:
    return f"https://{domain}"
