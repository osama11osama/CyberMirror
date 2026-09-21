"""Recursive query plan + pivot execution (#58)."""

import pytest

from app.models.schemas import Finding, IdentityProfile
from app.services.intelligence_pipeline import analyze_finding_pages_async
from app.services.investigation_budget import InvestigationBudget
from app.services.page_analyzer import artifact_from_http
from app.services.query_executor import canonicalize_result_url, execute_planned_query
from app.services.query_planner import PlannedQuery, QueryFamily, QueryState


REVIEW_PAGE = """
<html><body>
<h1>Hotel Aurora Review</h1>
<p>Posted by: RareHandle99</p>
<p>Stayed June 2026 for 3 nights as a solo traveller in Lisbon.</p>
<p>Reviewed 2026-07-10.</p>
<p>Contact: rarehandle99@example.com</p>
</body></html>
"""

SECOND_PAGE = """
<html><body>
<h1>Lisbon meetup notes</h1>
<p>Author: RareHandle99</p>
<p>Discussing hotels in Lisbon with rarehandle99@example.com</p>
</body></html>
"""


@pytest.mark.asyncio
async def test_seed_and_contextual_pivot_queries_execute(monkeypatch):
    """First planned search discovers a strong pivot; second contextual search runs."""
    calls: list[str] = []

    async def fake_search(query: str, max_results: int):
        calls.append(query)
        # Contextual pivots (email / location) return a second independent hit.
        if "example.com" in query or "Lisbon" in query or "lisbon" in query.lower():
            return [
                {
                    "href": "https://forum.example/lisbon-thread",
                    "title": "Lisbon meetup",
                    "body": "RareHandle99 in Lisbon",
                }
            ]
        return [
            {
                "href": "https://reviews.example/aurora",
                "title": "Hotel Aurora",
                "body": "Posted by RareHandle99",
            }
        ]

    async def fake_acquire(url, **kwargs):
        body = SECOND_PAGE if "lisbon-thread" in url else REVIEW_PAGE
        return artifact_from_http(
            source_url=url,
            body=body,
            status=200,
            final_url=url,
            title=kwargs.get("title") or "",
            scan_id=kwargs.get("scan_id") or "",
            budget=kwargs.get("budget"),
        )

    monkeypatch.setattr("app.services.intelligence_pipeline.acquire_page", fake_acquire)

    budget = InvestigationBudget(scan_id="pivot-e2e", max_generated_queries=12, max_pivot_depth=2)
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99"),
        [],  # no prior scan findings — pipeline must execute the plan
        scan_id="pivot-e2e",
        budget=budget,
        execute_queries=True,
        max_seed_queries=3,
        search_fn=fake_search,
        max_pages=6,
    )

    assert len(calls) >= 2
    assert any(
        "example.com" in q or "Lisbon" in q or "lisbon" in q.lower() for q in calls[1:]
    ), calls
    executed = payload["executed_queries"]
    assert executed
    assert any(q["state"] == "done" for q in executed)
    assert any(q["family"] == "contextual" for q in executed)
    assert payload["pivot_state"]["depth"] >= 1
    step_types = {s["step_type"] for s in payload["journal"]["steps"]}
    assert "pivot_generation" in step_types
    assert "generated_query" in step_types
    urls = {a["source_url"] for a in payload["artifacts"]}
    assert "https://reviews.example/aurora" in urls
    assert "https://forum.example/lisbon-thread" in urls


@pytest.mark.asyncio
async def test_weak_pivots_do_not_recurse_and_urls_dedupe(monkeypatch):
    calls: list[str] = []

    async def fake_search(query: str, max_results: int):
        calls.append(query)
        return [
            {
                "href": "https://tech.example/post",
                "title": "Python tip",
                "body": "Talking about Python and Docker only",
            }
        ]

    async def fake_acquire(url, **kwargs):
        return artifact_from_http(
            source_url=url,
            body="<p>Python and Docker discussion by nobody.</p>",
            status=200,
            final_url=url,
            title="tech",
            scan_id=kwargs.get("scan_id") or "",
            budget=kwargs.get("budget"),
        )

    monkeypatch.setattr("app.services.intelligence_pipeline.acquire_page", fake_acquire)
    budget = InvestigationBudget(scan_id="weak", max_generated_queries=8, max_pivot_depth=2)
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="alice"),
        [],
        scan_id="weak",
        budget=budget,
        max_seed_queries=2,
        search_fn=fake_search,
    )
    # Seed queries may run, but no contextual family should appear.
    assert all(q["family"] != "contextual" for q in payload["executed_queries"])
    assert payload["pivot_state"]["depth"] == 0


@pytest.mark.asyncio
async def test_cancellation_stops_subsequent_queries(monkeypatch):
    calls: list[str] = []

    async def fake_search(query: str, max_results: int):
        calls.append(query)
        return [{"href": "https://a.example/1", "title": "A", "body": "x"}]

    budget = InvestigationBudget(scan_id="cancel-q", max_generated_queries=10)
    budget.cancel()
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99"),
        [],
        scan_id="cancel-q",
        budget=budget,
        search_fn=fake_search,
        max_seed_queries=5,
    )
    assert calls == []
    assert payload["executed_queries"] == []
    assert any(s["status"] == "stopped" for s in payload["journal"]["steps"])


@pytest.mark.asyncio
async def test_execute_planned_query_marks_state_and_canonicalizes():
    async def fake_search(query: str, max_results: int):
        return [
            {"href": "https://WWW.Example.com/path/", "title": "T", "body": "S"},
            {"href": "https://www.example.com/path", "title": "dup", "body": "S"},
        ]

    pq = PlannedQuery(
        query='"RareHandle99"',
        family=QueryFamily.IDENTITY,
        reason="Exact quoted handle",
        priority=10,
    )
    budget = InvestigationBudget(scan_id="exec")
    findings = await execute_planned_query(
        pq, scan_id="exec", budget=budget, search_fn=fake_search
    )
    assert pq.state == QueryState.DONE
    assert budget.queries_used == 1
    assert len(findings) == 2
    assert canonicalize_result_url(findings[0].url) == canonicalize_result_url(
        findings[1].url
    )


@pytest.mark.asyncio
async def test_visited_urls_skip_repeat_acquisition(monkeypatch):
    acquires: list[str] = []

    async def fake_search(query: str, max_results: int):
        return [
            {
                "href": "https://reviews.example/aurora",
                "title": "same",
                "body": "x",
            }
        ]

    async def fake_acquire(url, **kwargs):
        acquires.append(url)
        return artifact_from_http(
            source_url=url,
            body=REVIEW_PAGE,
            status=200,
            final_url=url,
            title="r",
            scan_id=kwargs.get("scan_id") or "",
            budget=kwargs.get("budget"),
        )

    monkeypatch.setattr("app.services.intelligence_pipeline.acquire_page", fake_acquire)
    prior = Finding(
        platform="Web",
        title="prior",
        url="https://reviews.example/aurora",
        snippet="prior",
    )
    budget = InvestigationBudget(scan_id="dedupe", max_generated_queries=10)
    await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99"),
        [prior],
        scan_id="dedupe",
        budget=budget,
        search_fn=fake_search,
        max_seed_queries=2,
        max_pages=4,
    )
    assert acquires.count("https://reviews.example/aurora") == 1
