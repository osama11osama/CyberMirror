"""Playwright-based browser checks for bot-protected social platforms."""

import asyncio
import logging

from app.config import settings
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule

logger = logging.getLogger(__name__)

# (platform, url template, missing text fragments)
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
        if not username:
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

                for platform, url_tpl, missing_fragments in SOCIAL_TARGETS:
                    url = url_tpl.format(username=username)
                    try:
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        await asyncio.sleep(1.5)
                        text = (await page.content()).lower()
                        title = (await page.title()).lower()

                        if any(m in text or m in title for m in missing_fragments):
                            continue
                        if resp and resp.status >= 400:
                            continue

                        findings.append(Finding(
                            scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                            category=FindingCategory.SOCIAL, platform=platform,
                            title=f"Profile found on {platform}",
                            url=url,
                            description=f"Browser verified username '{username}'",
                            snippet=f"HTTP {resp.status if resp else '?'} · {await page.title()}",
                            confidence=0.88,
                            raw={"method": "playwright"},
                        ))
                    except Exception as exc:
                        logger.debug("Playwright %s check failed: %s", platform, exc)

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

        if not findings:
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="SocialBrowserModule",
                category=FindingCategory.SOCIAL, platform="Summary",
                title=f"No browser-verified social profiles for '{username}'",
                description="Profiles may be private, renamed, or require login.",
                confidence=0.3,
            ))

        return findings
