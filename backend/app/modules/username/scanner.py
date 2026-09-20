"""Catalog-driven username scanner with optional WhatsMyName dataset support."""

import asyncio
import logging
from urllib.parse import quote

import httpx

from app.engine.scan_context import check_cancelled, raise_if_cancelled
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.modules.username.wmn_loader import load_all_sites
from app.services.cache import get_cached_raw, set_cached_raw
from app.services.http_client import DEFAULT_HEADERS, get_with_retry
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)

CONCURRENCY = 8
TIMEOUT = 18
BATCH_SIZE = 40


class UsernameScanModule(NativeModule):
    id = "username_scan"
    name = "CyberMirror Username Scanner"
    description = "Checks public profile URLs for username presence"
    category = "username_discovery"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        username = profile.username.strip()
        if not username:
            return []

        sites = load_all_sites()
        if not sites:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="UsernameScanModule",
                category=FindingCategory.USERNAME, platform="System",
                title="No platform database loaded",
                description="Check backend logs for sites.json / WMN path",
                confidence=0.0,
            )]

        findings: list[Finding] = []
        sem = asyncio.Semaphore(CONCURRENCY)
        checked = 0
        errors = 0

        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            for i in range(0, len(sites), BATCH_SIZE):
                raise_if_cancelled(scan_id)
                batch_sites = sites[i : i + BATCH_SIZE]
                results = await asyncio.gather(*[
                    self._check_site(client, sem, site, username, scan_id)
                    for site in batch_sites
                ])
                for r in results:
                    if r is None:
                        checked += 1
                    elif isinstance(r, Finding):
                        findings.append(r)
                        checked += 1
                    elif r == "error":
                        errors += 1
                        checked += 1
                await throttle(0.25)

        logger.info(
            "Username scan '%s': %d platforms checked, %d found, %d errors",
            username, checked, len(findings), errors,
        )

        if check_cancelled(scan_id):
            return findings

        if not findings:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="UsernameScanModule",
                category=FindingCategory.USERNAME, platform="Summary",
                title=f"No direct username hits for '{username}'",
                description=(
                    f"Checked {checked} platforms. Some sites (Facebook, Instagram) "
                    "block automated checks — see Web Search and Social Browser results."
                ),
                confidence=0.3,
                raw={"platforms_checked": checked, "errors": errors},
            ))

        return findings

    async def _check_site(
        self, client: httpx.AsyncClient, sem: asyncio.Semaphore,
        site: dict, username: str, scan_id: str,
    ) -> Finding | None | str:
        if check_cancelled(scan_id):
            return None
        cache_key = f"username:{username}:{site['name']}"
        cached = get_cached_raw(cache_key)
        if cached == "miss":
            return None
        if isinstance(cached, dict) and cached.get("platform"):
            return Finding(**cached)

        async with sem:
            await throttle(0.08)
            url = site["url"].replace("{username}", quote(username, safe=""))
            try:
                resp = await get_with_retry(client, url)
                if not resp:
                    return "error"
                text = resp.text[:80000]
                if not self._profile_exists(resp.status_code, text, site):
                    set_cached_raw(cache_key, "miss")
                    return None
                finding = Finding(
                    scan_id=scan_id,
                    source=self.id,
                    provider="UsernameScanModule",
                    category=FindingCategory.USERNAME,
                    platform=site["name"],
                    title=f"Account found: {site['name']}",
                    url=url,
                    description=f"Username '{username}' · Category: {site.get('category', 'unknown')}",
                    snippet=f"HTTP {resp.status_code}",
                    confidence=0.92,
                    raw={"category": site.get("category"), "status": resp.status_code},
                )
                set_cached_raw(cache_key, finding.model_dump())
                return finding
            except Exception as exc:
                logger.debug("Check failed %s: %s", site.get("name"), exc)
                return "error"

    def _profile_exists(self, status: int, text: str, site: dict) -> bool:
        text_lower = text.lower()
        m_string = site.get("m_string") or site.get("missing_text") or ""
        m_code = site.get("m_code")

        if m_string and m_string.lower() in text_lower:
            if m_code is None or status == m_code:
                return False

        missing_status = site.get("missing_status") or []
        if missing_status and status in missing_status:
            e_string = site.get("e_string") or site.get("exists_text") or ""
            if not e_string or e_string.lower() not in text_lower:
                return False

        e_code = site.get("e_code")
        e_string = site.get("e_string") or site.get("exists_text") or ""

        if e_code is not None and status == e_code:
            if e_string:
                return e_string.lower() in text_lower
            return True

        exists_status = site.get("exists_status") or [200]
        if status in exists_status:
            if e_string:
                return e_string.lower() in text_lower
            if m_string and m_string.lower() in text_lower:
                return False
            return True

        return False
