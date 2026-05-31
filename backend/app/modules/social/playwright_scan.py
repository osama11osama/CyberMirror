"""Playwright-based browser checks for bot-protected social platforms."""

import asyncio
import logging
from urllib.parse import quote

from app.config import settings
from app.engine.scan_context import check_cancelled, raise_if_cancelled
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule

logger = logging.getLogger(__name__)

SOCIAL_TARGETS = (
    ("Facebook", "https://www.facebook.com/{username}/", ("page isn't available", "content isn't available", "page not found")),
    ("Instagram", "https://www.instagram.com/{username}/", ("sorry, this page isn't available", "page not found")),
    ("LinkedIn", "https://www.linkedin.com/in/{username}/", ("page not found", "this page doesn't exist")),
    ("TikTok", "https://www.tiktok.com/@{username}", ("couldn't find this account", "couldn't find this user")),
)


class SocialBrowserModule(NativeModule):
    id = "social_browser"
    name = "CyberMirror Social Browser"
    description = "Headless browser checks for Facebook, Instagram, LinkedIn, TikTok"
    category = "social_discovery"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        username = profile.username.strip()
        if not username and not profile.full_name:
            return []

        if not settings.playwright_enabled:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                category=FindingCategory.SOCIAL, platform="System",
                title="Social browser disabled",
                description="Enable in Settings → Playwright",
                confidence=0.0,
            )]

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                category=FindingCategory.SOCIAL, platform="System",
                title="Playwright not installed",
                description="Run: pip install playwright && playwright install chromium",
                confidence=0.0,
            )]

        findings: list[Finding] = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                )
                page = await context.new_page()

                if username:
                    for platform, url_tpl, missing_fragments in SOCIAL_TARGETS:
                        raise_if_cancelled(scan_id)
                        url = url_tpl.format(username=username)
                        hit = await self._check_url(page, platform, url, username, missing_fragments, scan_id)
                        if hit:
                            findings.append(hit)

                if profile.full_name:
                    raise_if_cancelled(scan_id)
                    fb_search = (
                        f"https://www.facebook.com/search/top?q={quote(profile.full_name)}"
                    )
                    try:
                        resp = await page.goto(fb_search, wait_until="domcontentloaded", timeout=25000)
                        await asyncio.sleep(2)
                        text = (await page.content()).lower()
                        if resp and resp.status < 400 and "no results" not in text:
                            findings.append(Finding(
                                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                                category=FindingCategory.SOCIAL, platform="Facebook Search",
                                title=f"Facebook search results for '{profile.full_name}'",
                                url=fb_search,
                                description="Name-based Facebook search returned content — review manually",
                                confidence=0.65,
                                raw={"method": "playwright_name_search"},
                            ))
                    except Exception as exc:
                        logger.debug("Facebook name search failed: %s", exc)

                if username:
                    fb_id_url = f"https://www.facebook.com/profile.php?id={quote(username)}"
                    try:
                        raise_if_cancelled(scan_id)
                        resp = await page.goto(fb_id_url, wait_until="domcontentloaded", timeout=20000)
                        await asyncio.sleep(1.5)
                        text = (await page.content()).lower()
                        if resp and resp.status < 400 and "page isn't available" not in text:
                            findings.append(Finding(
                                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                                category=FindingCategory.SOCIAL, platform="Facebook",
                                title="Possible Facebook profile (numeric/id URL)",
                                url=fb_id_url,
                                description=f"Browser check for username/id '{username}'",
                                confidence=0.6,
                            ))
                    except Exception as exc:
                        logger.debug("Facebook id URL check failed: %s", exc)

                await browser.close()
        except Exception as exc:
            logger.error("Playwright launch failed: %s", exc)
            return [Finding(
                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                category=FindingCategory.SOCIAL, platform="System",
                title="Browser engine error",
                description=str(exc)[:200],
                confidence=0.0,
            )]

        if check_cancelled(scan_id):
            return findings

        if not findings and username:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                category=FindingCategory.SOCIAL, platform="Summary",
                title=f"No browser-verified social profiles for '{username}'",
                description="Profiles may be private, renamed, or require login.",
                confidence=0.3,
            ))

        return findings

    async def _check_url(
        self, page, platform: str, url: str, username: str,
        missing_fragments: tuple, scan_id: str,
    ) -> Finding | None:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.5)
            text = (await page.content()).lower()
            title = (await page.title()).lower()

            if any(m in text or m in title for m in missing_fragments):
                return None
            if resp and resp.status >= 400:
                return None

            return Finding(
                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                category=FindingCategory.SOCIAL, platform=platform,
                title=f"Profile found on {platform}",
                url=url,
                description=f"Browser verified username '{username}'",
                snippet=f"HTTP {resp.status if resp else '?'} · {await page.title()}",
                confidence=0.88,
                raw={"method": "playwright"},
            )
        except Exception as exc:
            logger.debug("Playwright %s check failed: %s", platform, exc)
            return None
