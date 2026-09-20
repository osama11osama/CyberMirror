"""Ahmia Tor hidden-service index search — dark web mention detection."""

import asyncio
import logging
import re

from app.config import settings
from app.engine.scan_context import raise_if_cancelled
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.services.cache import get_cached, set_cached
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)

ONION_RE = re.compile(r"[a-z2-7]{16,56}\.onion", re.I)
AHMIA_URL = "https://ahmia.fi/"


def _build_queries(profile: IdentityProfile) -> list[tuple[str, str]]:
    """Return (query, label) pairs — skip overly short or generic terms."""
    queries: list[tuple[str, str]] = []
    email = profile.email.strip().lower()
    username = profile.username.strip()
    name = profile.full_name.strip()

    if email and "@" in email:
        queries.append((email, "email"))
    if username and len(username) >= 3:
        queries.append((username, "username"))
    if name and len(name) >= 4 and " " in name:
        queries.append((f'"{name}"', "name"))
    return queries[: settings.ahmia_max_queries]


def _matches_query(query: str, label: str, title: str, description: str, onion: str) -> bool:
    blob = f"{title} {description} {onion}".lower()
    q = query.strip('"').lower()
    if label == "email":
        return q in blob
    if label == "username":
        return q in blob or q in title.lower()
    return q in blob


def _onion_from_cite(cite: str) -> str:
    m = ONION_RE.search(cite or "")
    return m.group(0).lower() if m else (cite or "").strip()


class AhmiaSearchModule(NativeModule):
    id = "ahmia_search"
    name = "CyberMirror Ahmia Search"
    description = "Search Ahmia Tor index for mentions of your email, username, or name"
    category = "advanced_intelligence"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        queries = _build_queries(profile)
        if not queries:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="AhmiaSearchModule",
                category=FindingCategory.ADVANCED, platform="Ahmia",
                title="No search terms",
                description="Enter an email, username, or full name to search the Ahmia Tor index.",
                confidence=0.0,
            )]

        findings: list[Finding] = []
        seen_onions: set[str] = set()

        if settings.playwright_enabled:
            for query, label in queries:
                raise_if_cancelled(scan_id)
                batch = await self._playwright_search(query, label, scan_id, seen_onions)
                findings.extend(batch)
                if len(findings) >= settings.ahmia_max_results:
                    break

        if not findings:
            findings.extend(await self._ddgs_fallback(queries, scan_id, seen_onions))

        if not findings:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="AhmiaSearchModule",
                category=FindingCategory.ADVANCED, platform="Ahmia",
                title="No Tor index matches found",
                description=(
                    "Ahmia did not return indexed .onion pages matching your identity terms. "
                    "This does not guarantee absence from unindexed dark web content."
                ),
                confidence=0.7,
            ))

        return findings[: settings.ahmia_max_results]

    async def _playwright_search(
        self,
        query: str,
        label: str,
        scan_id: str,
        seen_onions: set[str],
    ) -> list[Finding]:
        cache_key = f"ahmia:{query}"
        cached = get_cached(cache_key)
        if cached is not None:
            return self._hits_to_findings(cached, query, label, scan_id, seen_onions)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        hits: list[dict] = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                await page.goto(AHMIA_URL, wait_until="networkidle", timeout=45000)
                inp = await page.query_selector('input[name="q"], input[type="search"], input')
                if not inp:
                    await browser.close()
                    return []
                await inp.fill(query.strip('"'))
                await inp.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=45000)
                await page.wait_for_timeout(2000)
                hits = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('.result')).slice(0, 40).map(r => ({
                        title: (r.querySelector('h4 a')?.innerText || '').trim(),
                        description: (r.querySelector('p')?.innerText || '').trim(),
                        onion: (r.querySelector('cite')?.innerText || '').trim(),
                        lastSeen: (r.querySelector('.lastSeen')?.innerText || '').trim(),
                    }))"""
                )
                await browser.close()
        except Exception as exc:
            logger.warning("Ahmia Playwright search failed: %s", exc)
            return []

        set_cached(cache_key, hits)
        return self._hits_to_findings(hits, query, label, scan_id, seen_onions)

    def _hits_to_findings(
        self,
        hits: list[dict],
        query: str,
        label: str,
        scan_id: str,
        seen_onions: set[str],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for hit in hits:
            title = hit.get("title") or "Tor hidden service"
            description = hit.get("description") or "No description provided"
            onion = _onion_from_cite(hit.get("onion") or "")
            if not onion or onion in seen_onions:
                continue
            if not _matches_query(query, label, title, description, onion):
                continue
            seen_onions.add(onion)
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="AhmiaSearchModule",
                category=FindingCategory.ADVANCED, platform="Ahmia / Tor",
                title=f"Tor index match: {title[:120]}",
                url=f"http://{onion}",
                description=(
                    f"Indexed .onion page matched your {label} in Ahmia's Tor search engine. "
                    "Verify manually — index text may be generic or unrelated."
                ),
                snippet=f"{onion} · {description[:200]} · last seen {hit.get('lastSeen', '?')}",
                confidence=0.72 if label == "email" else 0.62,
                raw={"query": query, "label": label, **hit},
            ))
            if len(findings) >= settings.ahmia_max_results:
                break
        return findings

    async def _ddgs_fallback(
        self,
        queries: list[tuple[str, str]],
        scan_id: str,
        seen_onions: set[str],
    ) -> list[Finding]:
        try:
            from ddgs import DDGS
        except ImportError:
            return []

        findings: list[Finding] = []
        for query, label in queries:
            raise_if_cancelled(scan_id)
            ddg_query = f'site:ahmia.fi "{query.strip(chr(34))}"'
            try:
                await throttle(1.2)
                with DDGS(timeout=20) as ddgs:
                    results = await asyncio.to_thread(
                        lambda q=ddg_query: list(ddgs.text(q, max_results=5))
                    )
                for item in results:
                    body = item.get("body") or ""
                    url = item.get("href") or item.get("link") or ""
                    onion_match = ONION_RE.search(body + " " + url)
                    onion = onion_match.group(0).lower() if onion_match else ""
                    if onion and onion in seen_onions:
                        continue
                    if onion:
                        seen_onions.add(onion)
                    findings.append(Finding(
                        scan_id=scan_id, source=self.id, provider="AhmiaSearchModule",
                        category=FindingCategory.ADVANCED, platform="Ahmia (web fallback)",
                        title=item.get("title") or f"Ahmia mention ({label})",
                        url=url or AHMIA_URL,
                        description=(
                            "Limited clearnet search fallback — enable Playwright for full Ahmia index search."
                        ),
                        snippet=body[:300],
                        confidence=0.45,
                    ))
            except Exception as exc:
                logger.debug("Ahmia DDGS fallback failed: %s", exc)
        return findings
