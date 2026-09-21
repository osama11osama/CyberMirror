"""Deep Page Analyzer — provenance-preserving public content capture (#37)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.evidence import BLOCK_MARKERS, EvidenceKind, EvidenceObservation, VerificationState
from app.services.investigation_budget import InvestigationBudget
from app.services.timeutil import utc_now


class AcquisitionMethod(str, Enum):
    HTTP = "http"
    PLAYWRIGHT = "playwright"
    SEARCH_SNIPPET = "search_snippet"
    BLOCKED = "blocked"
    ERROR = "error"
    UNSUPPORTED = "unsupported"


class PageArtifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_url: str = ""
    canonical_url: str = ""
    final_url: str = ""
    title: str = ""
    main_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    acquisition_method: AcquisitionMethod = AcquisitionMethod.HTTP
    collected_at: datetime = Field(default_factory=utc_now)
    http_status: int | None = None
    content_hash: str = ""
    blocked_reason: str | None = None
    evidence_id: str = ""
    scan_id: str = ""


_LOGIN_MARKERS = (
    "sign in",
    "log in",
    "login required",
    "create an account",
    "subscribe to continue",
)
_ERROR_MARKERS = ("404 not found", "page not found", "500 internal", "access denied")


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def detect_block_or_challenge(text: str, status: int | None = None) -> str | None:
    blob = (text or "").lower()
    if status in (401, 403, 429, 503):
        return f"http_{status}"
    for m in BLOCK_MARKERS:
        if m in blob:
            return f"challenge:{m}"
    for m in _LOGIN_MARKERS:
        if m in blob and len(blob) < 2500:
            return f"login_wall:{m}"
    for m in _ERROR_MARKERS:
        if m in blob and len(blob) < 2000:
            return f"error_page:{m}"
    return None


def prepare_main_text(html_or_text: str, budget: InvestigationBudget | None = None) -> str:
    """Strip crude chrome and cap size — not a full readability engine."""
    text = html_or_text or ""
    # Drop script/style blocks when HTML-ish.
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<nav[^>]*>.*?</nav>", " ", text)
    text = re.sub(r"(?is)<footer[^>]*>.*?</footer>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if budget:
        return budget.cap_content(text)
    return text[:400_000]


def artifact_from_http(
    *,
    source_url: str,
    body: str,
    status: int | None,
    final_url: str = "",
    title: str = "",
    canonical_url: str = "",
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
) -> PageArtifact:
    reason = detect_block_or_challenge(body, status)
    method = AcquisitionMethod.HTTP
    main = ""
    verification = VerificationState.LIKELY
    if reason:
        method = AcquisitionMethod.BLOCKED if "challenge" in reason or "login" in reason else AcquisitionMethod.ERROR
        verification = VerificationState.BLOCKED if method == AcquisitionMethod.BLOCKED else VerificationState.ERROR
        if budget:
            budget.record_blocked(source_url)
    else:
        main = prepare_main_text(body, budget)
    evidence = EvidenceObservation(
        kind=EvidenceKind.OBSERVATION,
        method=method.value,
        source_url=source_url,
        http_status=status,
        blocked_reason=reason,
        verification=verification,
        confidence_reason="deep_page_analyzer",
    )
    return PageArtifact(
        source_url=source_url,
        canonical_url=canonical_url or source_url,
        final_url=final_url or source_url,
        title=title,
        main_text=main,
        acquisition_method=method,
        http_status=status,
        content_hash=_hash_text(main or body[:2000]),
        blocked_reason=reason,
        evidence_id=evidence.id,
        scan_id=scan_id,
        metadata={"evidence": evidence.model_dump(mode="json")},
    )


def artifact_from_snippet(
    *,
    source_url: str,
    snippet: str,
    title: str = "",
    scan_id: str = "",
) -> PageArtifact:
    """Weaker evidence: indexed text only when destination is unavailable."""
    text = (snippet or "").strip()
    evidence = EvidenceObservation(
        kind=EvidenceKind.OBSERVATION,
        method=AcquisitionMethod.SEARCH_SNIPPET.value,
        source_url=source_url,
        verification=VerificationState.POSSIBLE,
        confidence_reason="search_index_snippet_only",
    )
    return PageArtifact(
        source_url=source_url,
        canonical_url=source_url,
        final_url=source_url,
        title=title,
        main_text=text[:4000],
        acquisition_method=AcquisitionMethod.SEARCH_SNIPPET,
        content_hash=_hash_text(text),
        evidence_id=evidence.id,
        scan_id=scan_id,
        metadata={"evidence": evidence.model_dump(mode="json"), "weaker_than": "direct_page"},
    )


async def acquire_page(
    url: str,
    *,
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
    prefer_playwright: bool = False,
    snippet_fallback: str = "",
    title: str = "",
) -> PageArtifact:
    """Acquire a public page respecting budgets; never bypasses protections."""
    if budget:
        stop = budget.consume_page(url)
        if stop:
            return PageArtifact(
                source_url=url,
                acquisition_method=AcquisitionMethod.UNSUPPORTED,
                blocked_reason=stop,
                scan_id=scan_id,
            )
        if budget.is_cancelled():
            return PageArtifact(
                source_url=url,
                acquisition_method=AcquisitionMethod.UNSUPPORTED,
                blocked_reason="cancelled",
                scan_id=scan_id,
            )

    timeout = budget.page_timeout_seconds if budget else 20.0
    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
            body = resp.text or ""
            art = artifact_from_http(
                source_url=url,
                body=body,
                status=resp.status_code,
                final_url=str(resp.url),
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
        if art.acquisition_method in (AcquisitionMethod.BLOCKED, AcquisitionMethod.ERROR) and snippet_fallback:
            return artifact_from_snippet(
                source_url=url, snippet=snippet_fallback, title=title, scan_id=scan_id
            )
        # Optional Playwright only when explicitly preferred and HTTP looks empty JS shell.
        if (
            prefer_playwright
            and art.acquisition_method == AcquisitionMethod.HTTP
            and len(art.main_text) < 80
            and budget
            and not budget.is_cancelled()
        ):
            rendered = await _try_playwright(url, timeout=timeout)
            if rendered is not None:
                return artifact_from_http(
                    source_url=url,
                    body=rendered,
                    status=200,
                    final_url=url,
                    title=title,
                    scan_id=scan_id,
                    budget=budget,
                ).model_copy(update={"acquisition_method": AcquisitionMethod.PLAYWRIGHT})
        return art
    except Exception as exc:  # noqa: BLE001 — acquisition errors are structured outcomes
        if snippet_fallback:
            return artifact_from_snippet(
                source_url=url, snippet=snippet_fallback, title=title, scan_id=scan_id
            )
        return PageArtifact(
            source_url=url,
            acquisition_method=AcquisitionMethod.ERROR,
            blocked_reason=f"request_error:{type(exc).__name__}",
            scan_id=scan_id,
        )


async def _try_playwright(url: str, timeout: float = 20.0) -> str | None:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            content = await page.content()
            await browser.close()
            return content
    except Exception:
        return None
