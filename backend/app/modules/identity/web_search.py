"""Native web search via DuckDuckGo — no external OSINT tools required."""

import asyncio
import logging
import time

from app.config import settings
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.modules.identity.queries import build_queries

from app.services.cache import get_cached, set_cached


class WebSearchModule(NativeModule):
    id = "web_search"
    name = "CyberMirror Web Search"
    description = "Public web search across the internet for name, username, email, phone"
    category = "identity_search"

    def __init__(
        self,
        max_queries: int | None = None,
        results_per_query: int | None = None,
        delay: float = 1.0,
    ):
        self.max_queries = max_queries or settings.web_search_max_queries
        self.results_per_query = results_per_query or settings.web_search_results_per_query
        self.delay = delay
        self._last_call = 0.0

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        try:
            from ddgs import DDGS
        except ImportError:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="WebSearchModule",
                category=FindingCategory.IDENTITY, platform="System",
                title="Missing dependency", description="Run: pip install ddgs",
                confidence=0.0,
            )]

        queries = build_queries(profile.model_dump())[: self.max_queries]
        if not queries:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="WebSearchModule",
                category=FindingCategory.IDENTITY, platform="System",
                title="No search terms",
                description="Enter at least a username, name, email, or phone number.",
                confidence=0.0,
            )]

        findings: list[Finding] = []
        queries_run = 0

        for query in queries:
            await self._rate_limit()
            cached = get_cached(query)
            if cached is not None:
                results = cached
            else:
                try:
                    with DDGS(timeout=25) as ddgs:
                        results = await asyncio.to_thread(
                            lambda q=query: list(ddgs.text(q, max_results=self.results_per_query))
                        )
                    set_cached(query, results)
                except Exception as exc:
                    logging.getLogger(__name__).warning("Web search failed for '%s': %s", query, exc)
                    continue
            queries_run += 1
            for item in results:
                href = item.get("href") or item.get("link") or ""
                title = item.get("title") or "Web result"
                snippet = item.get("body") or item.get("snippet") or ""
                platform = _platform_from_url(href)
                findings.append(Finding(
                    scan_id=scan_id,
                    source=self.id,
                    provider="WebSearchModule",
                    category=FindingCategory.IDENTITY,
                    platform=platform,
                    title=title,
                    url=href,
                    description=f"Found via search: {query}",
                    snippet=snippet[:500],
                    confidence=0.78,
                    raw={"query": query},
                ))

        if not findings and queries_run > 0:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="WebSearchModule",
                category=FindingCategory.IDENTITY, platform="Summary",
                title="No public web results",
                description=f"Ran {queries_run} searches — nothing indexed publicly for these terms.",
                confidence=0.2,
                raw={"queries_run": queries_run},
            ))

        return findings

    async def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last_call = time.monotonic()


def _platform_from_url(url: str) -> str:
    if not url:
        return "Web"
    url_lower = url.lower()
    for domain, label in (
        ("facebook.com", "Facebook"),
        ("instagram.com", "Instagram"),
        ("twitter.com", "Twitter/X"),
        ("x.com", "Twitter/X"),
        ("linkedin.com", "LinkedIn"),
        ("github.com", "GitHub"),
        ("reddit.com", "Reddit"),
        ("tiktok.com", "TikTok"),
        ("youtube.com", "YouTube"),
    ):
        if domain in url_lower:
            return label
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Web"
    except Exception:
        return "Web"
