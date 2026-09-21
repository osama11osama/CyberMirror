"""Playwright-based browser checks for bot-protected social platforms."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from app.config import settings
from app.engine.scan_context import check_cancelled, raise_if_cancelled
from app.models.evidence import (
    EvidenceKind,
    EvidenceObservation,
    VerificationState,
    confidence_for_verification,
    detect_block_reason,
    verification_to_outcome,
)
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile
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
                outcome=FindingOutcome.SYSTEM,
                verification=VerificationState.ERROR,
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
                outcome=FindingOutcome.SYSTEM,
                verification=VerificationState.ERROR,
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
                        hit = await self._check_url(
                            page, platform, url, username, missing_fragments, scan_id
                        )
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
                        title = (await page.title()).lower()
                        blocked = detect_block_reason(text, title)
                        if blocked:
                            findings.append(self._finding(
                                scan_id, "Facebook Search", fb_search, profile.full_name, "name",
                                VerificationState.BLOCKED,
                                title=f"Facebook search blocked ({blocked})",
                                description="Login/bot wall — not evidence of a profile",
                                http_status=resp.status if resp else None,
                                blocked_reason=blocked,
                                method="playwright_name_search",
                            ))
                        elif resp and resp.status < 400 and "no results" not in text:
                            findings.append(self._finding(
                                scan_id, "Facebook Search", fb_search, profile.full_name, "name",
                                VerificationState.POSSIBLE,
                                title=f"Facebook search results for '{profile.full_name}'",
                                description="Name-based Facebook search returned content — review manually",
                                http_status=resp.status if resp else None,
                                positive_markers=["search_content"],
                                method="playwright_name_search",
                                confidence_reason="Search page content without strong profile markers",
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
                        title = (await page.title()).lower()
                        blocked = detect_block_reason(text, title)
                        if blocked:
                            findings.append(self._finding(
                                scan_id, "Facebook", fb_id_url, username, "username",
                                VerificationState.BLOCKED,
                                title=f"Facebook id URL blocked ({blocked})",
                                description="Challenge/login wall — inconclusive",
                                http_status=resp.status if resp else None,
                                blocked_reason=blocked,
                                method="playwright",
                            ))
                        elif resp and resp.status < 400 and "page isn't available" not in text:
                            findings.append(self._finding(
                                scan_id, "Facebook", fb_id_url, username, "username",
                                VerificationState.POSSIBLE,
                                title="Possible Facebook profile (numeric/id URL)",
                                description=f"Browser check for username/id '{username}'",
                                http_status=resp.status if resp else None,
                                positive_markers=["http_ok"],
                                method="playwright",
                                confidence_reason="ID URL loaded without missing-page marker",
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
                outcome=FindingOutcome.SYSTEM,
                verification=VerificationState.ERROR,
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
                outcome=FindingOutcome.NEGATIVE,
                verification=VerificationState.NOT_FOUND,
            ))

        return findings

    def _finding(
        self,
        scan_id: str,
        platform: str,
        url: str,
        identifier: str,
        identifier_type: str,
        verification: VerificationState,
        *,
        title: str,
        description: str,
        http_status: int | None,
        method: str,
        positive_markers: list[str] | None = None,
        negative_markers: list[str] | None = None,
        blocked_reason: str | None = None,
        confidence_reason: str = "",
        page_title: str = "",
    ) -> Finding:
        evidence = EvidenceObservation(
            kind=EvidenceKind.OBSERVATION,
            method=method,
            queried_identifier=identifier,
            identifier_type=identifier_type,
            source_url=url,
            platform=platform,
            http_status=http_status,
            positive_markers=positive_markers or [],
            negative_markers=negative_markers or [],
            blocked_reason=blocked_reason,
            confidence_reason=confidence_reason or verification.value,
            verification=verification,
        )
        return Finding(
            scan_id=scan_id,
            source=self.id,
            provider="SocialBrowserModule",
            category=FindingCategory.SOCIAL,
            platform=platform,
            title=title,
            url=url,
            description=description,
            snippet=f"HTTP {http_status if http_status is not None else '?'} · {verification.value}"
            + (f" · {page_title}" if page_title else ""),
            confidence=confidence_for_verification(verification),
            outcome=verification_to_outcome(verification),
            verification=verification,
            evidence=evidence,
            raw={"method": method, "verification": verification.value},
        )

    async def _check_url(
        self, page, platform: str, url: str, username: str,
        missing_fragments: tuple, scan_id: str,
    ) -> Finding | None:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.5)
            text = (await page.content()).lower()
            page_title = await page.title()
            title_l = page_title.lower()
            status = resp.status if resp else None

            blocked = detect_block_reason(text, title_l)
            if blocked:
                return self._finding(
                    scan_id, platform, url, username, "username",
                    VerificationState.BLOCKED,
                    title=f"Check blocked on {platform}",
                    description=f"Bot/login wall ({blocked}) — not a verified profile",
                    http_status=status,
                    blocked_reason=blocked,
                    method="playwright",
                    page_title=page_title,
                    confidence_reason=f"Interstitial: {blocked}",
                )

            if any(m in text or m in title_l for m in missing_fragments):
                return None
            if status is not None and status >= 400:
                return None

            # Loaded without missing markers — likely, not verified (no platform e_string).
            return self._finding(
                scan_id, platform, url, username, "username",
                VerificationState.LIKELY,
                title=f"Likely profile on {platform}",
                description=f"Browser loaded '{username}' without missing-page markers",
                http_status=status,
                positive_markers=["no_missing_marker", f"http_{status}"],
                method="playwright",
                page_title=page_title,
                confidence_reason="Page loaded without known missing-account fragments",
            )
        except Exception as exc:
            logger.debug("Playwright %s check failed: %s", platform, exc)
            return None
