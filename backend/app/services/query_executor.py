"""Execute structured PlannedQuery objects via public web search (#58).

The default backend reuses DuckDuckGo (``ddgs``) like ``WebSearchModule``.
Tests inject a deterministic ``search_fn`` so CI never hits the live index.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

from app.config import settings
from app.models.schemas import Finding, FindingCategory
from app.services.investigation_budget import InvestigationBudget
from app.services.query_planner import PlannedQuery, QueryState

logger = logging.getLogger(__name__)

SearchFn = Callable[[str, int], Awaitable[list[dict]]]


class QuerySearchBackend(Protocol):
    async def __call__(self, query: str, max_results: int) -> list[dict]: ...


def canonicalize_result_url(url: str) -> str:
    """Normalize result URLs for visited-set dedupe (scheme/host/path only)."""
    value = (url or "").strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return value.lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower(), netloc, path, "", ""))


async def default_web_search(query: str, max_results: int) -> list[dict]:
    """Live public search via ddgs. Failures return an empty list."""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs not installed; planned query skipped")
        return []
    try:
        with DDGS(timeout=25) as ddgs:
            return await asyncio.to_thread(
                lambda: list(ddgs.text(query, max_results=max_results))
            )
    except Exception as exc:
        logger.warning("Planned query search failed for %r: %s", query, exc)
        return []


def _platform_from_url(url: str) -> str:
    if not url:
        return "Web"
    lower = url.lower()
    for domain, label in (
        ("github.com", "GitHub"),
        ("reddit.com", "Reddit"),
        ("tripadvisor.", "Tripadvisor"),
        ("booking.com", "Booking"),
    ):
        if domain in lower:
            return label
    try:
        host = urlsplit(url).netloc.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Web"
    except Exception:
        return "Web"


async def execute_planned_query(
    planned: PlannedQuery,
    *,
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
    search_fn: SearchFn | None = None,
    max_results: int | None = None,
    consume_budget: bool = True,
) -> list[Finding]:
    """Run one planned query and return public result findings.

    When ``consume_budget`` is False the caller already reserved the query slot
    (e.g. ``next_pivot_queries``).  On cancellation or budget stop the planned
    query state is updated and an empty list is returned.
    """
    limit = max_results if max_results is not None else settings.web_search_results_per_query
    limit = max(1, min(int(limit), 20))

    if budget is not None:
        if budget.is_cancelled():
            planned.state = QueryState.CANCELLED
            return []
        if consume_budget:
            stop = budget.consume_query()
            if stop:
                planned.state = (
                    QueryState.CANCELLED if stop == "cancelled" else QueryState.SKIPPED
                )
                return []

    planned.state = QueryState.RUNNING
    runner = search_fn or default_web_search
    try:
        raw_results = await runner(planned.query, limit)
    except Exception as exc:
        logger.warning("search_fn raised for %r: %s", planned.query, exc)
        planned.state = QueryState.SKIPPED
        return []

    if budget is not None and budget.is_cancelled():
        planned.state = QueryState.CANCELLED
        return []

    findings: list[Finding] = []
    for item in raw_results or []:
        href = str(item.get("href") or item.get("link") or item.get("url") or "").strip()
        if not href:
            continue
        title = str(item.get("title") or "Web result")
        snippet = str(item.get("body") or item.get("snippet") or "")
        findings.append(
            Finding(
                scan_id=scan_id,
                source="deep_query",
                provider="QueryExecutor",
                category=FindingCategory.IDENTITY,
                platform=_platform_from_url(href),
                title=title,
                url=href,
                description=f"Found via planned query: {planned.query}",
                snippet=snippet[:500],
                confidence=0.78,
                raw={
                    "query": planned.query,
                    "query_id": planned.id,
                    "family": planned.family.value,
                    "depth": planned.depth,
                    "reason": planned.reason,
                },
            )
        )

    planned.state = QueryState.DONE
    return findings
