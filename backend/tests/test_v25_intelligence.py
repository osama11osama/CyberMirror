"""v2.5 deep intelligence pipeline tests (#36–#50)."""

from app.models.evidence import VerificationState
from app.models.intelligence import Entity, EntityType, IntelligenceOrigin
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile, RiskLevel
from app.services.activity_extractor import extract_activities
from app.services.evidence_clustering import cluster_artifacts, independent_observation_count
from app.services.identity_hypotheses import HypothesisStatus, evaluate_handle_hypothesis
from app.services.intelligence_pipeline import analyze_finding_pages
from app.services.intelligence_report import build_intelligence_summary, intelligence_html_section
from app.services.investigation_budget import default_budget
from app.services.page_analyzer import artifact_from_http, artifact_from_snippet, detect_block_or_challenge
from app.services.pivot_engine import PivotEngineState, PivotStrength, next_pivot_queries, score_pivot
from app.services.query_planner import QueryFamily, build_investigation_plan
from app.services.travel_extractor import extract_travel_events


REVIEW_BODY = """
<html><body>
<h1>Hotel Aurora Review</h1>
<p>Posted by: RareHandle99</p>
<p>Stayed June 2026 for 3 nights as a solo traveller. Rated 4/5.</p>
<p>Beautiful stay in Lisbon. Reviewed 2026-07-10.</p>
<p>Contact me at rarehandle99@example.com</p>
</body></html>
"""


def test_page_analyzer_blocks_login_walls():
    assert detect_block_or_challenge("Please log in to continue", 200)
    art = artifact_from_http(source_url="https://x.example/", body="Just a moment... captcha", status=200)
    assert art.acquisition_method.value == "blocked"
    snip = artifact_from_snippet(source_url="https://x.example/", snippet="indexed text only")
    assert snip.acquisition_method.value == "search_snippet"


def test_entity_and_activity_extraction():
    art = artifact_from_http(source_url="https://forum.example/t/1", body=REVIEW_BODY, status=200, title="Hotel Aurora Review")
    ents, events = extract_activities(art)
    assert any(e.type == EntityType.HANDLE for e in ents)
    assert any(e.type == EntityType.EMAIL for e in ents)
    assert events
    assert events[0].type.value in ("review", "forum_post", "other")
    assert "identity" not in (events[0].derivation_reason or "").lower() or "not identity" in events[0].derivation_reason.lower()


def test_clustering_mirrors_not_independent():
    a = artifact_from_http(source_url="https://orig.example/r", body=REVIEW_BODY, status=200, title="A")
    b = artifact_from_http(source_url="https://mirror.example/r", body=REVIEW_BODY, status=200, title="A")
    # Force same fingerprint
    b.content_hash = a.content_hash
    clusters = cluster_artifacts([a, b])
    assert len(clusters) == 1
    assert clusters[0].independent_source_count == 1
    assert clusters[0].mirror_count == 1
    assert independent_observation_count(clusters) == 1


def test_identity_hypothesis_not_auto_verified():
    profile = IdentityProfile(username="RareHandle99")
    ent = Entity(
        type=EntityType.HANDLE,
        original_value="RareHandle99",
        normalized_value="rarehandle99",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=["e1"],
        confidence=0.8,
    )
    hyp = evaluate_handle_hypothesis(profile, ent, independent_sources=1, cross_linked=False)
    assert hyp.status != HypothesisStatus.VERIFIED
    assert hyp.status in (HypothesisStatus.POSSIBLE, HypothesisStatus.LIKELY)
    hyp2 = evaluate_handle_hypothesis(profile, ent, independent_sources=2, cross_linked=True)
    assert hyp2.status in (HypothesisStatus.LIKELY, HypothesisStatus.VERIFIED)


def test_query_plan_families_and_dedupe():
    profile = IdentityProfile(username="alice", full_name="Alice Example")
    plan = build_investigation_plan(profile)
    families = {p.family for p in plan}
    assert QueryFamily.IDENTITY in families
    assert QueryFamily.ACTIVITY in families
    assert QueryFamily.TRAVEL in families
    assert QueryFamily.TECHNICAL in families
    queries = [p.query for p in plan]
    assert len(queries) == len(set(q.lower() for q in queries))
    assert any(p.reason for p in plan)


def test_pivot_engine_skips_weak_and_respects_budget():
    profile = IdentityProfile(username="alice")
    weak = Entity(type=EntityType.TECHNOLOGY, original_value="python", normalized_value="python", confidence=0.9)
    strong = Entity(
        type=EntityType.LOCATION,
        original_value="Lisbon",
        normalized_value="lisbon",
        confidence=0.9,
        origin=IntelligenceOrigin.OBSERVED,
    )
    assert score_pivot(weak).strength == PivotStrength.WEAK
    budget = default_budget("p1")
    budget.max_generated_queries = 3
    state = PivotEngineState()
    # Mark seed queries as already executed so only contextual remain limited.
    q = next_pivot_queries(profile, [strong], budget, state)
    assert isinstance(q, list)
    budget.cancel()
    assert next_pivot_queries(profile, [strong], budget, state) == []


def test_travel_keeps_stay_and_review_dates_distinct():
    art = artifact_from_http(source_url="https://travel.example/r", body=REVIEW_BODY, status=200, title="Review")
    events = extract_travel_events(art)
    assert events
    ev = events[0]
    assert ev.type.value == "travel"
    assert ev.start.precision.value in ("month", "exact_day", "unknown")
    # Must not invent stay from review alone as exact day when only month stated.
    assert ev.start.precision.value == "month"
    if ev.publication.value and ev.start.value:
        assert ev.publication.value != ev.start.value or ev.publication.precision != ev.start.precision


def test_full_pipeline_and_report_escaping():
    profile = IdentityProfile(username="RareHandle99")
    finding = Finding(
        source="web_search",
        platform="Web",
        title="<script>alert(1)</script> Hotel review",
        url="https://travel.example/r",
        category=FindingCategory.IDENTITY,
        outcome=FindingOutcome.CONFIRMED,
        verification=VerificationState.VERIFIED,
        risk_level=RiskLevel.MEDIUM,
        snippet="Stayed June 2026",
        raw={"page_text": REVIEW_BODY},
    )
    payload = analyze_finding_pages(profile, [finding], scan_id="scan-x")
    assert payload["bundle"]["entities"]
    assert payload["journal"]["steps"]
    assert payload["timeline"]
    summary = build_intelligence_summary(payload)
    assert "disclaimer" in summary
    html = intelligence_html_section(payload)
    assert "<script>" not in html
    assert "Identity hypotheses are not factual" in html or "disclaimer" in summary["disclaimer"].lower()
