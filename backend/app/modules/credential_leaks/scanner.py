"""Credential leak checks — HIBP breaches, paste dumps, and web fallback."""

import asyncio
import logging

from app.config import settings
from app.engine.scan_context import raise_if_cancelled
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile
from app.modules.base import NativeModule
from app.services.hibp_client import fetch_breaches, fetch_pastes
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)

PASTE_SITES = (
    "pastebin.com",
    "ghostbin.com",
    "rentry.co",
    "paste.ee",
)


class CredentialLeaksModule(NativeModule):
    id = "credential_leaks"
    name = "CyberMirror Credential Leaks"
    description = "Breaches, paste dumps, and credential exposure (HIBP + web fallback)"
    category = "email_exposure"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        email = profile.email.strip().lower()
        if not email:
            return [Finding(
                scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
                category=FindingCategory.EMAIL, platform="System",
                title="No email provided",
                description="Add an email address to run credential leak checks.",
                confidence=0.0,
                outcome=FindingOutcome.SYSTEM,
                raw={"outcome": FindingOutcome.SYSTEM.value},
            )]

        findings: list[Finding] = []
        has_api = bool(settings.hibp_api_key)

        if has_api:
            raise_if_cancelled(scan_id)
            breach_result = await fetch_breaches(email)
            findings.extend(self._breach_findings(email, scan_id, breach_result.items))
            raise_if_cancelled(scan_id)
            paste_result = await fetch_pastes(email)
            findings.extend(self._paste_findings(email, scan_id, paste_result.items))

            if findings:
                return findings

            if breach_result.ok and paste_result.ok:
                return [Finding(
                    scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
                    category=FindingCategory.EMAIL, platform="HIBP",
                    title=f"No credential leaks found for {email}",
                    description=(
                        "HIBP reports no breaches or paste dumps for this email. "
                        "Rotate passwords periodically and enable MFA."
                    ),
                    confidence=0.92,
                    outcome=FindingOutcome.NEGATIVE,
                    raw={"outcome": FindingOutcome.NEGATIVE.value},
                )]

            errors = ", ".join(
                e for e in (breach_result.error, paste_result.error) if e
            ) or "request_failed"
            return [Finding(
                scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
                category=FindingCategory.EMAIL, platform="HIBP",
                title="Credential check inconclusive",
                description=(
                    "HIBP could not be queried successfully, so absence of leaks was not verified. "
                    f"Details: {errors}"
                ),
                confidence=0.35,
                outcome=FindingOutcome.INCONCLUSIVE,
                raw={"outcome": FindingOutcome.INCONCLUSIVE.value, "errors": errors},
            )]

        findings.extend(await self._web_fallback(email, scan_id))
        if findings:
            return findings
        return [Finding(
            scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
            category=FindingCategory.EMAIL, platform="HIBP",
            title="Credential check inconclusive",
            description=(
                "No HIBP API key configured — only limited paste-site web search was used. "
                "Add your key in Settings for authoritative breach and paste results."
            ),
            confidence=0.35,
            outcome=FindingOutcome.INCONCLUSIVE,
            raw={"outcome": FindingOutcome.INCONCLUSIVE.value},
        )]

    def _breach_findings(self, email: str, scan_id: str, breaches: list[dict]) -> list[Finding]:
        findings: list[Finding] = []
        for breach in breaches:
            name = breach.get("Name", "Unknown")
            data_classes = breach.get("DataClasses") or []
            has_passwords = any("password" in dc.lower() for dc in data_classes)
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
                category=FindingCategory.EMAIL, platform="HIBP Breach",
                title=f"Breached: {name}",
                url=f"https://haveibeenpwned.com/account/{email}",
                description=breach.get("Description", "")[:400],
                snippet=(
                    f"Date: {breach.get('BreachDate', '?')} · "
                    f"Data: {', '.join(data_classes[:6])}"
                    + (" · passwords included" if has_passwords else "")
                ),
                confidence=0.97,
                outcome=FindingOutcome.CONFIRMED,
                raw={"type": "breach", "outcome": FindingOutcome.CONFIRMED.value, **breach},
            ))
        return findings

    def _paste_findings(self, email: str, scan_id: str, pastes: list[dict]) -> list[Finding]:
        findings: list[Finding] = []
        for paste in pastes:
            source = paste.get("Source", "Paste")
            paste_id = paste.get("Id", "?")
            findings.append(Finding(
                scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
                category=FindingCategory.EMAIL, platform=f"HIBP Paste ({source})",
                title=f"Email in paste dump: {source}",
                url=f"https://haveibeenpwned.com/Pastes/{email}",
                description=(
                    f"Your email appeared in a public paste ({source}). "
                    "Treat associated passwords as compromised."
                ),
                snippet=(
                    f"Paste ID: {paste_id} · Date: {paste.get('Date', '?')} · "
                    f"Emails in paste: {paste.get('EmailCount', '?')}"
                ),
                confidence=0.94,
                outcome=FindingOutcome.CONFIRMED,
                raw={"type": "paste", "outcome": FindingOutcome.CONFIRMED.value, **paste},
            ))
        return findings

    async def _web_fallback(self, email: str, scan_id: str) -> list[Finding]:
        try:
            from ddgs import DDGS
        except ImportError:
            return []

        findings: list[Finding] = []
        queries = [
            f'site:haveibeenpwned.com "{email}"',
            f'"{email}" paste leak',
        ]
        for site in PASTE_SITES[:2]:
            queries.append(f'site:{site} "{email}"')

        seen_urls: set[str] = set()
        for query in queries:
            raise_if_cancelled(scan_id)
            try:
                await throttle(1.0)
                with DDGS(timeout=20) as ddgs:
                    results = await asyncio.to_thread(
                        lambda q=query: list(ddgs.text(q, max_results=4))
                    )
                for item in results:
                    url = item.get("href") or item.get("link") or ""
                    if not url or url in seen_urls:
                        continue
                    body = (item.get("body") or "").lower()
                    if email not in body and email not in (item.get("title") or "").lower():
                        continue
                    seen_urls.add(url)
                    platform = "Paste site" if any(s in url for s in PASTE_SITES) else "Web"
                    findings.append(Finding(
                        scan_id=scan_id, source=self.id, provider="CredentialLeaksModule",
                        category=FindingCategory.EMAIL, platform=platform,
                        title=item.get("title") or "Possible credential exposure",
                        url=url,
                        description=(
                            "Web search hit — add HIBP API key in Settings for verified results."
                        ),
                        snippet=(item.get("body") or "")[:300],
                        confidence=0.5,
                        outcome=FindingOutcome.CONFIRMED,
                        raw={"outcome": FindingOutcome.CONFIRMED.value},
                    ))
            except Exception as exc:
                logger.debug("Credential web search failed for %s: %s", query, exc)
        return findings
