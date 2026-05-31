"""Phone number discovery via public web search."""

import asyncio
import logging
import time

from app.config import settings
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.services.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

PHONE_QUERIES = (
    '"{phone}"',
    '"{phone}" whatsapp',
    '"{phone}" telegram',
    '"{phone}" facebook',
    'site:truecaller.com "{phone}"',
    'site:facebook.com "{phone}"',
    "{phone} contact",
)


class PhoneScanModule(NativeModule):
    id = "phone_scan"
    name = "CyberMirror Phone Scanner"
    description = "Search the public web for phone number exposure"
    category = "identity_search"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        phone = profile.phone.strip()
        if not phone:
            return []

        try:
            from ddgs import DDGS
        except ImportError:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="PhoneScanModule",
                category=FindingCategory.IDENTITY, platform="System",
                title="Missing dependency", description="Run: pip install ddgs",
                confidence=0.0,
            )]

        findings: list[Finding] = []
        queries = [q.format(phone=phone) for q in PHONE_QUERIES][:8]

        for query in queries:
            cached = get_cached(query)
            if cached is not None:
                results = cached
            else:
                try:
                    with DDGS(timeout=25) as ddgs:
                        results = await asyncio.to_thread(
                            lambda q=query: list(ddgs.text(q, max_results=5))
                        )
                    set_cached(query, results)
                except Exception as exc:
                    logger.warning("Phone search failed '%s': %s", query, exc)
                    continue
                time.sleep(0.8)

            for item in results:
                href = item.get("href") or item.get("link") or ""
                findings.append(Finding(
                    scan_id=scan_id,
                    source=self.id,
                    provider="PhoneScanModule",
                    category=FindingCategory.IDENTITY,
                    platform=_platform(href),
                    title=item.get("title") or "Phone mention",
                    url=href,
                    description=f"Phone found via: {query}",
                    snippet=(item.get("body") or item.get("snippet") or "")[:500],
                    confidence=0.72,
                    raw={"query": query, "phone": phone},
                ))

        return findings


def _platform(url: str) -> str:
    u = url.lower()
    for d, n in (("truecaller", "Truecaller"), ("whatsapp", "WhatsApp"), ("facebook", "Facebook")):
        if d in u:
            return n
    return "Web"
