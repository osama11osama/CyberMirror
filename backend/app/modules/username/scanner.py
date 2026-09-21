"""Catalog-driven username scanner with optional WhatsMyName dataset support."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

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
from app.modules.username.wmn_loader import load_all_sites
from app.services.cache import get_cached_raw, set_cached_raw
from app.services.http_client import DEFAULT_HEADERS, get_with_retry
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)

CONCURRENCY = 8
TIMEOUT = 18
BATCH_SIZE = 40


@dataclass
class _Assess:
    verification: VerificationState
    positive_markers: list[str] = field(default_factory=list)
    negative_markers: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    confidence_reason: str = ""


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
                outcome=FindingOutcome.SYSTEM,
                verification=VerificationState.ERROR,
            )]

        findings: list[Finding] = []
        sem = asyncio.Semaphore(CONCURRENCY)
        checked = 0
        errors = 0
        blocked = 0

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
                        if r.verification == VerificationState.BLOCKED:
                            blocked += 1
                    elif r == "error":
                        errors += 1
                        checked += 1
                await throttle(0.25)

        logger.info(
            "Username scan '%s': %d platforms checked, %d findings, %d blocked, %d errors",
            username, checked, len(findings), blocked, errors,
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
                outcome=FindingOutcome.NEGATIVE,
                verification=VerificationState.NOT_FOUND,
                raw={"platforms_checked": checked, "errors": errors, "blocked": blocked},
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
            try:
                return Finding(**cached)
            except Exception:
                pass

        async with sem:
            await throttle(0.08)
            url = site["url"].replace("{username}", quote(username, safe=""))
            try:
                resp = await get_with_retry(client, url)
                if not resp:
                    return "error"
                text = resp.text[:80000]
                assess = self._assess_response(resp.status_code, text, site)

                if assess.verification == VerificationState.NOT_FOUND:
                    set_cached_raw(cache_key, "miss")
                    return None

                if assess.verification == VerificationState.ERROR:
                    return "error"

                # Emit findings for verified/likely/possible/blocked/inconclusive.
                if assess.verification not in (
                    VerificationState.VERIFIED,
                    VerificationState.LIKELY,
                    VerificationState.POSSIBLE,
                    VerificationState.BLOCKED,
                    VerificationState.INCONCLUSIVE,
                ):
                    set_cached_raw(cache_key, "miss")
                    return None

                evidence = EvidenceObservation(
                    kind=EvidenceKind.OBSERVATION,
                    method="http",
                    queried_identifier=username,
                    identifier_type="username",
                    source_url=url,
                    platform=site["name"],
                    http_status=resp.status_code,
                    positive_markers=assess.positive_markers,
                    negative_markers=assess.negative_markers,
                    blocked_reason=assess.blocked_reason,
                    confidence_reason=assess.confidence_reason,
                    verification=assess.verification,
                    extras={"category": site.get("category")},
                )
                title = {
                    VerificationState.VERIFIED: f"Account verified: {site['name']}",
                    VerificationState.LIKELY: f"Likely account: {site['name']}",
                    VerificationState.POSSIBLE: f"Possible account: {site['name']}",
                    VerificationState.BLOCKED: f"Check blocked: {site['name']}",
                    VerificationState.INCONCLUSIVE: f"Inconclusive: {site['name']}",
                }.get(assess.verification, f"Account signal: {site['name']}")

                finding = Finding(
                    scan_id=scan_id,
                    source=self.id,
                    provider="UsernameScanModule",
                    category=FindingCategory.USERNAME,
                    platform=site["name"],
                    title=title,
                    url=url,
                    description=(
                        f"Username '{username}' · {assess.confidence_reason} · "
                        f"Category: {site.get('category', 'unknown')}"
                    ),
                    snippet=f"HTTP {resp.status_code} · {assess.verification.value}",
                    confidence=confidence_for_verification(assess.verification),
                    outcome=verification_to_outcome(assess.verification),
                    verification=assess.verification,
                    evidence=evidence,
                    raw={
                        "category": site.get("category"),
                        "status": resp.status_code,
                        "verification": assess.verification.value,
                    },
                )
                set_cached_raw(cache_key, finding.model_dump(mode="json"))
                return finding
            except Exception as exc:
                logger.debug("Check failed %s: %s", site.get("name"), exc)
                return "error"

    def _assess_response(self, status: int, text: str, site: dict) -> _Assess:
        """Classify response — HTTP 200 alone is never VERIFIED without positive markers."""
        text_lower = text.lower()
        m_string = site.get("m_string") or site.get("missing_text") or ""
        m_code = site.get("m_code")
        e_code = site.get("e_code")
        e_string = site.get("e_string") or site.get("exists_text") or ""
        missing_status = site.get("missing_status") or []
        exists_status = site.get("exists_status") or [200]

        blocked = detect_block_reason(text_lower)
        if blocked:
            return _Assess(
                VerificationState.BLOCKED,
                blocked_reason=blocked,
                confidence_reason=f"Challenge/login interstitial ({blocked})",
            )

        # Explicit negative markers (WhatsMyName-style).
        if m_string and m_string.lower() in text_lower:
            if m_code is None or status == m_code:
                return _Assess(
                    VerificationState.NOT_FOUND,
                    negative_markers=[m_string],
                    confidence_reason="Missing-account marker matched",
                )

        if missing_status and status in missing_status:
            if not e_string or e_string.lower() not in text_lower:
                return _Assess(
                    VerificationState.NOT_FOUND,
                    negative_markers=[f"http_{status}"],
                    confidence_reason="HTTP status listed as missing-account",
                )

        positives: list[str] = []
        if e_string and e_string.lower() in text_lower:
            positives.append(e_string)

        if e_code is not None and status == e_code:
            if e_string:
                if positives:
                    return _Assess(
                        VerificationState.VERIFIED,
                        positive_markers=positives,
                        confidence_reason="Exists HTTP code + positive text marker",
                    )
                return _Assess(
                    VerificationState.POSSIBLE,
                    positive_markers=[f"http_{status}"],
                    confidence_reason="Exists HTTP code without positive text marker",
                )
            return _Assess(
                VerificationState.POSSIBLE,
                positive_markers=[f"http_{status}"],
                confidence_reason="Exists HTTP code only — not high-confidence verified",
            )

        if status in exists_status:
            if positives:
                return _Assess(
                    VerificationState.VERIFIED if status == 200 else VerificationState.LIKELY,
                    positive_markers=positives + [f"http_{status}"],
                    confidence_reason="Positive text marker with expected HTTP status",
                )
            if m_string and m_string.lower() in text_lower:
                return _Assess(
                    VerificationState.NOT_FOUND,
                    negative_markers=[m_string],
                    confidence_reason="Missing marker present on exists-status response",
                )
            # HTTP 200 (or listed exists status) alone → possible, never verified.
            return _Assess(
                VerificationState.POSSIBLE,
                positive_markers=[f"http_{status}"],
                confidence_reason="HTTP status alone is insufficient for verified",
            )

        return _Assess(
            VerificationState.NOT_FOUND,
            confidence_reason="No positive existence criteria matched",
        )
