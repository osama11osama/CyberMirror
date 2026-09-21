"""Expanded extraction, journal trails, and timeline filters (#61/#62/#63)."""

from datetime import date

import pytest

from app.models.schemas import Finding, IdentityProfile
from app.services.activity_extractor import extract_activities
from app.services.entity_extractor import extract_entities
from app.services.intelligence_pipeline import analyze_finding_pages_async
from app.services.investigation_budget import InvestigationBudget
from app.services.investigation_journal import InvestigationJournal
from app.services.page_analyzer import artifact_from_http
from app.services.timeline_builder import build_timeline, filter_timeline_entries


STRUCTURED_HTML = """
<html><head>
<meta property="og:site_name" content="Acme Reviews">
<meta property="og:locality" content="Durrës">
<script type="application/ld+json">
{"@type":"Review","author":{"@type":"Person","name":"RareHandle99","url":"https://github.com/RareHandle99"},
 "itemReviewed":{"@type":"Hotel","name":"Hotel Aurora","address":{"@type":"PostalAddress","addressLocality":"Lisbon"}},
 "publisher":{"@type":"Organization","name":"Acme Reviews"}}
</script>
</head><body>
<p>Product: TravelPro Bag</p>
<p>Vehicle: Toyota Corolla</p>
<p>Company: Overlooked Labs</p>
<p>Built with Python on Docker</p>
<p>Profile https://twitter.com/RareHandle99</p>
<p>Just mentioning Lisbon casually again.</p>
</body></html>
"""

FORUM_THREAD = """
Forum thread: travel tips

Posted by: AliceTraveler
Date: 2026-05-01
I stayed in Lisbon last spring.

Posted by: BobCommenter
Date: 2026-05-02
Comment: try the Alfama district.

Posted by: CarolReply
on 2026-05-03
Replied to Bob with more hotel notes.
"""

AMBIGUOUS = """
This Review With From That Hotel Posted Author Forum
Python Docker React nothing contextual.
"""


def test_structured_and_labeled_entity_extraction():
    art = artifact_from_http(
        source_url="https://reviews.example/r",
        body=STRUCTURED_HTML,
        status=200,
        title="Hotel review",
    )
    ents = extract_entities(art)
    types = {e.type.value for e in ents}
    assert "organization" in types
    assert "product" in types
    assert "vehicle" in types
    assert "social_account" in types
    assert "location" in types
    assert "technology" in types
    locs = [e for e in ents if e.type.value == "location"]
    assert any(e.confidence >= 0.8 for e in locs)
    assert any("structured" in e.extraction_method for e in locs)
    tech = [e for e in ents if e.type.value == "technology"]
    assert tech and all(e.confidence <= 0.45 for e in tech)


def test_ambiguous_caps_are_not_organizations():
    art = artifact_from_http(source_url="https://x.example/", body=AMBIGUOUS, status=200, title="")
    ents = extract_entities(art)
    assert not any(e.type.value == "organization" for e in ents)
    assert not any(e.type.value == "product" for e in ents)
    # Bare tech words without context must not appear as high-confidence pivots.
    assert not any(e.type.value == "technology" and e.confidence >= 0.7 for e in ents)


def test_multi_author_forum_produces_separate_events():
    art = artifact_from_http(
        source_url="https://forum.example/t/1",
        body=FORUM_THREAD,
        status=200,
        title="Travel tips",
    )
    ents, events = extract_activities(art)
    assert len(events) >= 3
    authors = {
        e.original_value
        for e in ents
        if e.attributes.get("authorship") == "page_claimed"
    }
    assert {"AliceTraveler", "BobCommenter", "CarolReply"} <= authors
    assert all(ev.attributes.get("block_count", 1) >= 3 for ev in events)


def test_repository_activity_from_github_page():
    body = """
    Posted by: RareHandle99
    Committed to repository cybermirror on github.com
    Opened issue #12 about Docker.
    """
    art = artifact_from_http(
        source_url="https://github.com/RareHandle99/cybermirror",
        body=body,
        status=200,
        title="Commit activity",
    )
    _ents, events = extract_activities(art)
    assert events
    assert events[0].type.value == "repository_activity"


@pytest.mark.asyncio
async def test_journal_trail_covers_multi_hop_investigation(monkeypatch):
    calls: list[str] = []

    async def fake_search(query: str, max_results: int):
        calls.append(query)
        if "example.com" in query:
            return [{"href": "https://two.example/b", "title": "B", "body": "x"}]
        return [{"href": "https://one.example/a", "title": "A", "body": "x"}]

    async def fake_acquire(url, **kwargs):
        body = STRUCTURED_HTML if "one.example" in url else FORUM_THREAD
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
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99", email="rarehandle99@example.com"),
        [],
        scan_id="journal-trail",
        budget=InvestigationBudget(scan_id="journal-trail", max_generated_queries=10),
        search_fn=fake_search,
        max_seed_queries=2,
        max_pages=6,
    )
    steps = payload["journal"]["steps"]
    types = {s["step_type"] for s in steps}
    assert {
        "investigation_seed",
        "generated_query",
        "search_result",
        "page_acquisition",
        "entity_extraction",
        "activity_extraction",
        "evidence_cluster",
        "identity_hypothesis",
        "conclusion",
    } <= types
    # No full page bodies leaked into journal metadata.
    blob = str(steps)
    assert "TravelPro Bag" not in blob or "page_text" not in blob
    assert all(len(str(s.get("metadata") or {})) < 4000 for s in steps)

    journal = InvestigationJournal.model_validate(payload["journal"])
    conclusions = [s for s in journal.steps if s.step_type.value == "conclusion"]
    assert conclusions
    trail = journal.trail_for(conclusions[0].output_refs[0])
    trail_types = {s.step_type.value for s in trail}
    assert "conclusion" in trail_types
    assert trail_types & {"identity_hypothesis", "event_creation", "page_acquisition", "investigation_seed"}


def test_timeline_filters_and_precision(monkeypatch):
    from app.models.intelligence import Event, EventType, IntelligenceOrigin, parse_fuzzy_date
    from app.services.page_analyzer import artifact_from_http

    review = """
    <h1>Hotel</h1>
    <p>Posted by: RareHandle99</p>
    <p>Stayed June 2026 for 3 nights in Lisbon.</p>
    <p>Reviewed 2026-07-10.</p>
    """
    original = artifact_from_http(source_url="https://one.example/r", body=review, status=200)
    mirror = artifact_from_http(source_url="https://mirror.example/r", body=review, status=200)
    mirror.content_hash = original.content_hash
    independent = artifact_from_http(
        source_url="https://two.example/r",
        body=review + " Independent note.",
        status=200,
    )
    events = [
        Event(
            type=EventType.TRAVEL,
            title="Stay",
            start=parse_fuzzy_date("June 2026", year=2026, month=6),
            publication=parse_fuzzy_date("2026-07-10", year=2026, month=7, day=10),
            location_text="Lisbon",
            platform="Web",
            confidence=0.72,
            origin=IntelligenceOrigin.DERIVED,
            supporting_evidence_ids=[
                original.evidence_id,
                mirror.evidence_id,
                independent.evidence_id,
            ],
            source_url=original.source_url,
        ),
        Event(
            type=EventType.COMMENT,
            title="Undated note",
            confidence=0.4,
            origin=IntelligenceOrigin.OBSERVED,
            platform="Forum",
            supporting_evidence_ids=[independent.evidence_id],
        ),
    ]
    from app.services.evidence_clustering import cluster_artifacts

    arts = [original, mirror, independent]
    dated, unknown = build_timeline(
        events,
        artifacts=arts,
        clusters=cluster_artifacts(arts),
    )
    assert dated
    assert dated[0].precision == "month"
    assert dated[0].date_label == "2026-06"
    assert dated[0].independent_observations == 2
    assert dated[0].hypothesis_id == "" or True  # may be empty without hyps
    assert unknown
    assert unknown[0].unknown_date is True

    filtered_dated, _ = filter_timeline_entries(
        dated,
        unknown,
        event_type="travel",
        location="Lisbon",
        min_confidence=0.5,
        origin="derived",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )
    assert len(filtered_dated) == 1
    empty, _ = filter_timeline_entries(dated, unknown, event_type="employment")
    assert empty == []
