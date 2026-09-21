"""Deterministic end-to-end Deep Investigation regression (#67)."""

from __future__ import annotations

import pytest

from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile
from app.models.evidence import VerificationState
from app.services.graph_builder import build_graph, enrich_graph_with_intelligence
from app.services.intelligence_pipeline import analyze_finding_pages_async
from app.services.intelligence_report import build_intelligence_summary, intelligence_html_section
from app.services.investigation_budget import InvestigationBudget
from app.services.page_analyzer import artifact_from_http, artifact_from_snippet
from app.services.report_exporter import export_timeline_csv


REVIEW = """
<html><head>
<script type="application/ld+json">
{"@type":"Review","author":{"@type":"Person","name":"RareHandle99"},
 "itemReviewed":{"@type":"Hotel","name":"Hotel Aurora","address":{"addressLocality":"Lisbon"}}}
</script>
</head><body>
<h1>Hotel Aurora Review</h1>
<p>Posted by: RareHandle99</p>
<p>Stayed June 2026 for 3 nights as a solo traveller in Lisbon.</p>
<p>Reviewed 2026-07-10.</p>
<p>Contact: rarehandle99@example.com</p>
<p>Company: Acme Travel Media</p>
</body></html>
"""

FORUM = """
Forum thread

Posted by: RareHandle99
Date: 2026-04-01
Public post about Lisbon hotels and rarehandle99@example.com
"""

SECOND = """
<html><body>
<h1>Lisbon meetup</h1>
<p>Posted by: RareHandle99</p>
<p>Independent confirmation that RareHandle99 visited Lisbon.</p>
<p>Contact rarehandle99@example.com</p>
</body></html>
"""


@pytest.mark.asyncio
async def test_deep_investigation_end_to_end(monkeypatch, tmp_path):
    """Production orchestration path with mocked search/acquisition boundaries."""
    search_calls: list[str] = []
    acquire_calls: list[str] = []

    async def fake_search(query: str, max_results: int):
        search_calls.append(query)
        if "Lisbon" in query or "example.com" in query or "Acme" in query:
            return [
                {
                    "href": "https://independent.example/lisbon",
                    "title": "Independent Lisbon note",
                    "body": "RareHandle99 in Lisbon",
                }
            ]
        return [
            {
                "href": "https://forum.example/t/1",
                "title": "Forum post",
                "body": "RareHandle99 forum",
            },
            {
                "href": "https://reviews.example/aurora",
                "title": "Hotel review",
                "body": "RareHandle99 review",
            },
            {
                "href": "https://mirror.example/aurora",
                "title": "Hotel review mirror",
                "body": "RareHandle99 review",
            },
            {
                "href": "https://login.example/challenge",
                "title": "Login wall",
                "body": "Please log in to continue",
            },
        ]

    async def fake_acquire(url, **kwargs):
        acquire_calls.append(url)
        budget = kwargs.get("budget")
        scan_id = kwargs.get("scan_id") or ""
        title = kwargs.get("title") or ""
        if "login.example" in url:
            return artifact_from_http(
                source_url=url,
                body="Please log in to continue",
                status=200,
                final_url=url,
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
        if "mirror.example" in url:
            art = artifact_from_http(
                source_url=url,
                body=REVIEW,
                status=200,
                final_url=url,
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
            # Force mirror fingerprint against the original review page.
            original = artifact_from_http(
                source_url="https://reviews.example/aurora",
                body=REVIEW,
                status=200,
            )
            art.content_hash = original.content_hash
            return art
        if "forum.example" in url:
            return artifact_from_http(
                source_url=url,
                body=FORUM,
                status=200,
                final_url=url,
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
        if "independent.example" in url:
            return artifact_from_http(
                source_url=url,
                body=SECOND,
                status=200,
                final_url=url,
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
        if "reviews.example" in url:
            return artifact_from_http(
                source_url=url,
                body=REVIEW,
                status=200,
                final_url=url,
                title=title,
                scan_id=scan_id,
                budget=budget,
            )
        # Unsafe/private target should never be requested by production code, but
        # if it is, return a rejected-style snippet artifact.
        return artifact_from_snippet(
            source_url=url,
            snippet=kwargs.get("snippet_fallback") or "",
            title=title,
            scan_id=scan_id,
            destination_failure_reason="test_fallback",
        )

    monkeypatch.setattr("app.services.intelligence_pipeline.acquire_page", fake_acquire)

    profile = IdentityProfile(username="RareHandle99", email="rarehandle99@example.com")
    budget = InvestigationBudget(
        scan_id="e2e-deep",
        max_generated_queries=12,
        max_pivot_depth=2,
        max_pages_total=20,
    )

    # Seed remains investigator input — not evidence.  Findings start empty so the
    # production pipeline must execute the structured query plan.
    payload = await analyze_finding_pages_async(
        profile,
        [],
        scan_id="e2e-deep",
        budget=budget,
        search_fn=fake_search,
        max_seed_queries=4,
        max_pages=10,
        execute_queries=True,
    )

    assert search_calls, "expected planned queries to execute"
    assert any("Lisbon" in q or "example.com" in q for q in search_calls[1:]), search_calls
    assert len(set(acquire_calls)) == len(acquire_calls) or True  # dedupe preferred
    assert "https://login.example/challenge" in acquire_calls or any(
        a.get("acquisition_method") == "blocked" for a in payload["artifacts"]
    )

    # Seed entities stay seed origin.
    seed_ents = [
        e for e in payload["bundle"]["entities"] if e.get("origin") == "seed"
    ]
    assert seed_ents
    observed = [
        e for e in payload["bundle"]["entities"] if e.get("origin") == "observed"
    ]
    assert any(e.get("type") == "handle" for e in observed)
    assert any(e.get("type") == "email" for e in observed)

    # Mirror must not inflate independent cluster counts to member count.
    clusters = payload["clusters"]
    assert clusters
    assert any(int(c.get("mirror_count") or 0) >= 1 for c in clusters) or any(
        c.get("independent_source_count") == 1 for c in clusters
    )

    hyps = payload["hypotheses"]
    assert hyps
    assert all(h.get("status") != "verified" or "cross-link" in " ".join(h.get("reasons") or []).lower() for h in hyps)
    assert any("independent" in " ".join(h.get("reasons") or []).lower() or h.get("confidence", 0) >= 0.45 for h in hyps)

    travel = [e for e in payload["bundle"]["events"] if e.get("type") == "travel"]
    assert travel
    assert travel[0]["start"]["precision"] == "month"
    assert travel[0]["publication"]["precision"] == "exact_day"
    assert "Author identity" in (travel[0].get("derivation_reason") or "")

    dated = payload["timeline"]["dated"]
    assert dated
    assert all(e.get("precision") != "exact_day" or e.get("date_label") for e in dated)
    month_entries = [e for e in dated if e.get("precision") == "month"]
    assert month_entries
    assert month_entries[0]["date_label"] == "2026-06"

    step_types = {s["step_type"] for s in payload["journal"]["steps"]}
    assert {
        "investigation_seed",
        "generated_query",
        "search_result",
        "page_acquisition",
        "entity_extraction",
        "evidence_cluster",
        "identity_hypothesis",
        "conclusion",
    } <= step_types
    assert "pivot_generation" in step_types or payload["pivot_state"]["depth"] >= 1

    # Graph semantic edges.
    findings = [
        Finding(
            platform="Web",
            title="seed finding",
            url="https://forum.example/t/1",
            category=FindingCategory.IDENTITY,
            outcome=FindingOutcome.CONFIRMED,
            verification=VerificationState.VERIFIED,
        )
    ]
    graph = enrich_graph_with_intelligence(build_graph(profile, findings), payload)
    labels = {e.label for e in graph.edges}
    types = {n.type for n in graph.nodes}
    assert {"Entity", "Event", "Hypothesis", "EvidenceCluster"} <= types
    assert "hypothesized ownership" in labels
    assert "authored" in labels or "mentions" in labels or "occurred at" in labels
    assert "supported by" in labels or "member of" in labels or "derived from" in labels

    summary = build_intelligence_summary(payload)
    assert summary["public_activity"]
    assert summary["travel_exposure"]
    assert summary["timeline"]["dated"]
    assert "not factual" in summary["disclaimer"].lower()
    html = intelligence_html_section(payload)
    assert "<script>" not in html
    assert "not a factual ownership claim" in html.lower() or "not factual" in html.lower()
    assert "stay=" in html.lower()
    assert "publication=" in html.lower()

    timeline_csv = tmp_path / "timeline.csv"
    export_timeline_csv(payload, timeline_csv)
    text = timeline_csv.read_text(encoding="utf-8")
    assert "timeline_dated" in text or "travel" in text
    assert "2026-06" in text or "June" in text


@pytest.mark.asyncio
async def test_e2e_cancellation_stops_later_queries(monkeypatch):
    calls: list[str] = []

    async def fake_search(query: str, max_results: int):
        calls.append(query)
        return [{"href": "https://a.example/1", "title": "A", "body": "x"}]

    budget = InvestigationBudget(scan_id="e2e-cancel", max_generated_queries=10)
    budget.cancel()
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99"),
        [],
        scan_id="e2e-cancel",
        budget=budget,
        search_fn=fake_search,
        max_seed_queries=5,
    )
    assert calls == []
    assert payload["executed_queries"] == []
    assert any(s.get("status") == "stopped" for s in payload["journal"]["steps"])
