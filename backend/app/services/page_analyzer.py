"""Deep Page Analyzer — provenance-preserving public content capture (#37)."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.evidence import BLOCK_MARKERS, EvidenceKind, EvidenceObservation, VerificationState
from app.services.investigation_budget import InvestigationBudget
from app.services.public_target import TargetValidation, validate_public_target_async
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


@dataclass(frozen=True)
class _BoundedResponse:
    status_code: int
    url: str
    headers: dict[str, str]
    body: str
    is_redirect: bool
    truncated: bool = False


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


def _canonical_from_html(body: str, base_url: str) -> str:
    for tag in re.findall(r"(?is)<link\b[^>]*>", body or ""):
        rel = re.search(r"(?is)\brel\s*=\s*['\"]([^'\"]+)['\"]", tag)
        href = re.search(r"(?is)\bhref\s*=\s*['\"]([^'\"]+)['\"]", tag)
        if not rel or not href or "canonical" not in rel.group(1).lower().split():
            continue
        candidate = urljoin(base_url, href.group(1).strip())
        if urlsplit(candidate).scheme.lower() in {"http", "https"}:
            return candidate
    return ""


def detect_block_or_challenge(text: str, status: int | None = None) -> str | None:
    blob = (text or "").lower()
    # Any non-success HTTP status is an acquisition failure — never extract
    # entities from unrecognized 4xx/5xx bodies as if they were public pages.
    if status is not None and not (200 <= int(status) < 300):
        if status in (401, 403, 429, 503):
            return f"http_{status}"
        if 400 <= int(status) < 600:
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
    """Strip crude chrome and cap size — not a full readability engine.

    Newlines are preserved so multi-author forum blocks remain separable.
    """
    text = html_or_text or ""
    # Drop script/style blocks when HTML-ish.
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<nav[^>]*>.*?</nav>", " ", text)
    text = re.sub(r"(?is)<footer[^>]*>.*?</footer>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)</div\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
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
    from app.services.structured_page import parse_structured_signals

    structured = parse_structured_signals(body or "")
    evidence = EvidenceObservation(
        kind=EvidenceKind.OBSERVATION,
        method=method.value,
        source_url=source_url,
        http_status=status,
        blocked_reason=reason,
        verification=verification,
        confidence_reason="deep_page_analyzer",
    )
    resolved_final_url = final_url or source_url
    return PageArtifact(
        source_url=source_url,
        canonical_url=canonical_url or _canonical_from_html(body, resolved_final_url) or source_url,
        final_url=resolved_final_url,
        title=title,
        main_text=main,
        acquisition_method=method,
        http_status=status,
        content_hash=_hash_text(main or body[:2000]),
        blocked_reason=reason,
        evidence_id=evidence.id,
        scan_id=scan_id,
        metadata={
            "evidence": evidence.model_dump(mode="json"),
            "structured": {
                "organizations": structured.organizations[:12],
                "products": structured.products[:12],
                "locations": structured.locations[:12],
                "authors": structured.authors[:12],
                "social_profiles": structured.social_profiles[:12],
                "vehicles": structured.vehicles[:12],
            },
        },
    )


def artifact_from_snippet(
    *,
    source_url: str,
    snippet: str,
    title: str = "",
    scan_id: str = "",
    destination_failure_reason: str | None = None,
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
        metadata={
            "evidence": evidence.model_dump(mode="json"),
            "weaker_than": "direct_page",
            **(
                {"destination_failure_reason": destination_failure_reason}
                if destination_failure_reason
                else {}
            ),
        },
    )


async def acquire_page(
    url: str,
    *,
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
    prefer_playwright: bool = False,
    snippet_fallback: str = "",
    title: str = "",
    transport: Any | None = None,
) -> PageArtifact:
    """Acquire a public page respecting budgets; never bypasses protections."""
    if budget and budget.is_cancelled():
        return _cancelled_artifact(url, scan_id=scan_id)
    validation = await validate_public_target_async(url)
    if not validation.allowed:
        if snippet_fallback:
            return artifact_from_snippet(
                source_url=url,
                snippet=snippet_fallback,
                title=title,
                scan_id=scan_id,
                destination_failure_reason=validation.reason or "target_rejected",
            )
        return _rejected_artifact(url, validation, scan_id=scan_id)
    if budget:
        stop = budget.consume_page(url)
        if stop:
            return _structured_outcome_artifact(
                url,
                method=AcquisitionMethod.UNSUPPORTED,
                reason=stop,
                verification=VerificationState.BLOCKED,
                scan_id=scan_id,
            )
        if budget.is_cancelled():
            return _cancelled_artifact(url, scan_id=scan_id)

    timeout = budget.page_timeout_seconds if budget else 20.0
    try:
        import httpx

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            transport=transport,
        ) as client:
            request_url = url
            redirect_count = 0
            deadline = asyncio.get_running_loop().time() + timeout
            max_body_bytes = budget.max_extracted_content_bytes if budget else 400_000
            while True:
                if budget and budget.is_cancelled():
                    return _cancelled_artifact(url, scan_id=scan_id)
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("page acquisition deadline exceeded")
                resp = await asyncio.wait_for(
                    _bounded_get(client, request_url, max_body_bytes),
                    timeout=remaining,
                )
                if not resp.is_redirect:
                    break
                redirect_count += 1
                if redirect_count > 8:
                    return _rejected_artifact(
                        url,
                        TargetValidation(False, request_url, "too_many_redirects"),
                        scan_id=scan_id,
                    )
                location = resp.headers.get("location", "")
                next_url = urljoin(resp.url, location)
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("page acquisition deadline exceeded")
                redirect_validation = await asyncio.wait_for(
                    validate_public_target_async(next_url),
                    timeout=remaining,
                )
                if not redirect_validation.allowed:
                    if snippet_fallback:
                        return artifact_from_snippet(
                            source_url=url,
                            snippet=snippet_fallback,
                            title=title,
                            scan_id=scan_id,
                            destination_failure_reason=redirect_validation.reason
                            or "redirect_rejected",
                        )
                    return _rejected_artifact(
                        url,
                        redirect_validation,
                        scan_id=scan_id,
                        final_url=next_url,
                    )
                if budget:
                    stop = budget.consume_page(next_url)
                    if stop:
                        return _structured_outcome_artifact(
                            url,
                            final_url=next_url,
                            method=AcquisitionMethod.UNSUPPORTED,
                            reason=stop,
                            verification=VerificationState.BLOCKED,
                            scan_id=scan_id,
                        )
                request_url = next_url
            body = resp.body
            art = artifact_from_http(
                source_url=url,
                body=body,
                status=resp.status_code,
                final_url=resp.url,
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
            if resp.truncated:
                art.metadata["content_truncated"] = True
        if art.acquisition_method in (AcquisitionMethod.BLOCKED, AcquisitionMethod.ERROR) and snippet_fallback:
            return artifact_from_snippet(
                source_url=url,
                snippet=snippet_fallback,
                title=title,
                scan_id=scan_id,
                destination_failure_reason=art.blocked_reason,
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
                rendered_body, rendered_url = rendered
                rendered_artifact = artifact_from_http(
                    source_url=url,
                    body=rendered_body,
                    status=200,
                    final_url=rendered_url,
                    title=title,
                    scan_id=scan_id,
                    budget=budget,
                )
                # A rendered login/CAPTCHA/error state must retain its blocked
                # classification instead of being relabeled as successful.
                if rendered_artifact.acquisition_method == AcquisitionMethod.HTTP:
                    rendered_artifact.acquisition_method = AcquisitionMethod.PLAYWRIGHT
                return rendered_artifact
        return art
    except Exception as exc:  # noqa: BLE001 — acquisition errors are structured outcomes
        if snippet_fallback:
            return artifact_from_snippet(
                source_url=url,
                snippet=snippet_fallback,
                title=title,
                scan_id=scan_id,
                destination_failure_reason=f"request_error:{type(exc).__name__}",
            )
        return _structured_outcome_artifact(
            url,
            method=AcquisitionMethod.ERROR,
            reason=f"request_error:{type(exc).__name__}",
            verification=VerificationState.ERROR,
            scan_id=scan_id,
        )


async def _bounded_get(client: Any, url: str, max_bytes: int) -> _BoundedResponse:
    """Read at most ``max_bytes`` from an untrusted response body."""
    chunks = bytearray()
    truncated = False
    async with client.stream("GET", url) as response:
        is_redirect = response.status_code in {301, 302, 303, 307, 308}
        if not is_redirect:
            async for chunk in response.aiter_bytes():
                remaining = max_bytes - len(chunks)
                if remaining <= 0:
                    truncated = True
                    break
                chunks.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True
                    break
        encoding = response.encoding or "utf-8"
        try:
            body = bytes(chunks).decode(encoding, errors="replace")
        except LookupError:
            body = bytes(chunks).decode("utf-8", errors="replace")
        return _BoundedResponse(
            status_code=response.status_code,
            url=str(response.url),
            headers=dict(response.headers),
            body=body,
            is_redirect=is_redirect,
            truncated=truncated,
        )


def _rejected_artifact(
    source_url: str,
    validation: TargetValidation,
    *,
    scan_id: str,
    final_url: str = "",
) -> PageArtifact:
    reason = f"unsafe_target:{validation.reason or 'not_public'}"
    evidence = EvidenceObservation(
        kind=EvidenceKind.OBSERVATION,
        method=AcquisitionMethod.UNSUPPORTED.value,
        source_url=source_url,
        blocked_reason=reason,
        verification=VerificationState.BLOCKED,
        confidence_reason="public_target_policy",
    )
    return PageArtifact(
        source_url=source_url,
        final_url=final_url,
        acquisition_method=AcquisitionMethod.UNSUPPORTED,
        blocked_reason=reason,
        evidence_id=evidence.id,
        scan_id=scan_id,
        metadata={
            "evidence": evidence.model_dump(mode="json"),
            "target_validation": {
                "host": validation.host,
                "reason": validation.reason,
                "resolved_addresses": list(validation.resolved_addresses),
            },
        },
    )


def _cancelled_artifact(source_url: str, *, scan_id: str) -> PageArtifact:
    return _structured_outcome_artifact(
        source_url=source_url,
        method=AcquisitionMethod.UNSUPPORTED,
        reason="cancelled",
        verification=VerificationState.BLOCKED,
        scan_id=scan_id,
    )


def _structured_outcome_artifact(
    source_url: str,
    *,
    method: AcquisitionMethod,
    reason: str,
    verification: VerificationState,
    scan_id: str,
    final_url: str = "",
) -> PageArtifact:
    evidence = EvidenceObservation(
        kind=EvidenceKind.OBSERVATION,
        method=method.value,
        source_url=source_url,
        blocked_reason=reason,
        verification=verification,
        confidence_reason="deep_page_analyzer_outcome",
    )
    return PageArtifact(
        source_url=source_url,
        final_url=final_url,
        acquisition_method=method,
        blocked_reason=reason,
        evidence_id=evidence.id,
        scan_id=scan_id,
        metadata={"evidence": evidence.model_dump(mode="json")},
    )


async def _try_playwright(url: str, timeout: float = 20.0) -> tuple[str, str] | None:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()

            async def guard(route) -> None:
                request_url = route.request.url
                validation = await validate_public_target_async(request_url)
                if validation.allowed:
                    await route.continue_()
                else:
                    await route.abort("blockedbyclient")

            await context.route("**/*", guard)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            final_validation = await validate_public_target_async(page.url)
            if not final_validation.allowed:
                await browser.close()
                return None
            content = await page.content()
            final_url = page.url
            await browser.close()
            return content, final_url
    except Exception:
        return None
