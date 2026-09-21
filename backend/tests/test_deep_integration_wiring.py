"""Production-path wiring for acquisition, lineage, travel, and lifecycle."""

import pytest

from app.engine.scan_engine import ScanEngine
from app.models.intelligence import Entity, EntityType, IntelligenceOrigin
from app.models.intelligence import Event, EventType
from app.models.schemas import Finding, IdentityProfile
from app.services.evidence_clustering import cluster_artifacts
from app.services.evidence_lineage import EvidenceLineageIndex, independent_sources_by_entity
from app.services.intelligence_pipeline import analyze_finding_pages_async
from app.services.investigation_budget import (
    InvestigationBudget,
    clear_budget,
    default_budget,
    get_budget,
)
from app.services.page_analyzer import artifact_from_http
from app.services.timeline_builder import build_timeline


REVIEW = """
<h1>Hotel Aurora Review</h1>
<p>Posted by: RareHandle99</p>
<p>Stayed June 2026 for 3 nights as a solo traveller in Lisbon.</p>
<p>Reviewed 2026-07-10.</p>
"""


@pytest.mark.asyncio
async def test_pipeline_acquires_url_only_finding(monkeypatch):
    calls = []

    async def fake_acquire(url, **kwargs):
        calls.append((url, kwargs["budget"]))
        return artifact_from_http(
            source_url=url,
            body=REVIEW,
            status=200,
            final_url=url,
            title=kwargs["title"],
            scan_id=kwargs["scan_id"],
            budget=kwargs["budget"],
        )

    monkeypatch.setattr("app.services.intelligence_pipeline.acquire_page", fake_acquire)
    budget = InvestigationBudget(scan_id="acquire")
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99"),
        [Finding(platform="Web", title="Review", url="https://public.example/review")],
        scan_id="acquire",
        budget=budget,
    )
    assert calls == [("https://public.example/review", budget)]
    assert payload["artifacts"][0]["acquisition_method"] == "http"
    step_types = {step["step_type"] for step in payload["journal"]["steps"]}
    assert {"search_result", "page_acquisition", "entity_extraction", "conclusion"} <= step_types


def test_lineage_counts_mirrors_once_and_independent_sources_separately():
    original = artifact_from_http(source_url="https://one.example/r", body=REVIEW, status=200)
    mirror = artifact_from_http(source_url="https://mirror.example/r", body=REVIEW, status=200)
    independent = artifact_from_http(
        source_url="https://two.example/r",
        body=REVIEW + " Independent confirmation.",
        status=200,
    )
    artifacts = [original, mirror, independent]
    lineage = EvidenceLineageIndex.build(artifacts, cluster_artifacts(artifacts))
    entities = [
        Entity(
            type=EntityType.HANDLE,
            normalized_value="rarehandle99",
            original_value="RareHandle99",
            origin=IntelligenceOrigin.OBSERVED,
            supporting_evidence_ids=[artifact.evidence_id],
        )
        for artifact in artifacts
    ]
    counts = independent_sources_by_entity(entities, lineage)
    assert set(counts.values()) == {2}

    from app.services.evidence_lineage import coalesce_identity_entities
    from app.services.identity_hypotheses import build_identity_hypotheses

    coalesced = coalesce_identity_entities(entities)
    assert len(coalesced) == 1
    assert set(coalesced[0].supporting_evidence_ids) == {
        original.evidence_id,
        mirror.evidence_id,
        independent.evidence_id,
    }
    hyp = build_identity_hypotheses(
        IdentityProfile(username="RareHandle99"),
        coalesced,
        independent_by_entity=independent_sources_by_entity(coalesced, lineage),
    )[0]
    assert len(hyp.supporting_evidence_ids) >= 2
    assert "independent" in " ".join(hyp.reasons).lower() or hyp.confidence >= 0.45

    event = Event(
        type=EventType.OTHER,
        supporting_evidence_ids=[
            original.evidence_id,
            mirror.evidence_id,
            independent.evidence_id,
        ],
    )
    _dated, unknown = build_timeline(
        [event],
        artifacts=artifacts,
        clusters=cluster_artifacts(artifacts),
    )
    assert unknown[0].independent_observations == 2


@pytest.mark.asyncio
async def test_pipeline_uses_identity_for_travel_and_suppresses_mirror():
    findings = [
        Finding(platform="Web", title="Original", url="https://one.example/r", raw={"page_text": REVIEW}),
        Finding(platform="Web", title="Mirror", url="https://mirror.example/r", raw={"page_text": REVIEW}),
    ]
    payload = await analyze_finding_pages_async(
        IdentityProfile(username="RareHandle99"),
        findings,
        scan_id="lineage",
        budget=InvestigationBudget(scan_id="lineage"),
    )
    travel = [event for event in payload["bundle"]["events"] if event["type"] == "travel"]
    assert len(travel) == 1
    assert travel[0]["start"]["precision"] == "month"
    assert travel[0]["publication"]["precision"] == "exact_day"
    assert "Author identity" in travel[0]["derivation_reason"]
    assert payload["clusters"][0]["independent_source_count"] == 1


def test_scan_cancellation_cancels_registered_budget(monkeypatch):
    budget = default_budget("cancel-me")
    monkeypatch.setattr("app.engine.scan_engine.get_scan", lambda _scan_id: {"scan": {"status": "running"}})
    monkeypatch.setattr("app.engine.job_store.cancel_job", lambda _scan_id: True)
    assert ScanEngine().cancel_scan("cancel-me")
    assert budget.is_cancelled()
    clear_budget("cancel-me")


@pytest.mark.asyncio
async def test_scan_completion_cleans_budget_registry(monkeypatch):
    engine = ScanEngine()
    default_budget("clean-me")

    async def no_findings(_scan_id, _profile, _modules):
        return []

    monkeypatch.setattr(engine, "_execute_modules", no_findings)
    monkeypatch.setattr("app.engine.scan_engine.is_cancelled", lambda _scan_id: False)
    monkeypatch.setattr("app.engine.scan_engine.delete_findings_for_scan", lambda _scan_id: None)
    monkeypatch.setattr("app.engine.scan_engine.save_findings", lambda _findings: None)
    monkeypatch.setattr("app.engine.scan_engine.update_scan_status", lambda *_args: None)
    monkeypatch.setattr("app.engine.scan_engine.complete_job", lambda *_args: None)
    monkeypatch.setattr("app.engine.scan_engine.update_job", lambda *_args, **_kwargs: None)

    await engine.run_scan_background("clean-me", IdentityProfile(username="seed"), [])
    assert get_budget("clean-me") is None
