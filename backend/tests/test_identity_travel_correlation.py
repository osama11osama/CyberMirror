"""Identity cross-links, contradictions, and travel confidence wiring (#59/#60)."""

from app.models.intelligence import Entity, EntityType, IntelligenceOrigin
from app.models.schemas import Finding, IdentityProfile
from app.services.evidence_clustering import cluster_artifacts
from app.services.evidence_lineage import EvidenceLineageIndex, coalesce_identity_entities
from app.services.identity_hypotheses import (
    HypothesisStatus,
    build_identity_hypotheses,
    detect_contradicting_evidence,
    detect_cross_linked_entity_ids,
    evaluate_handle_hypothesis,
)
from app.services.intelligence_pipeline import analyze_finding_pages
from app.services.page_analyzer import artifact_from_http
from app.services.travel_extractor import extract_travel_events


REVIEW = """
<html><body>
<h1>Hotel Aurora Review</h1>
<p>Posted by: RareHandle99</p>
<p>Stayed June 2026 for 3 nights as a solo traveller in Lisbon.</p>
<p>Reviewed 2026-07-10.</p>
<p>Contact: rarehandle99@example.com</p>
</body></html>
"""

OTHER_AUTHOR = """
<html><body>
<h1>Hotel Aurora Review</h1>
<p>Posted by: OtherPerson42</p>
<p>Stayed June 2026 for 3 nights as a solo traveller in Lisbon.</p>
<p>Reviewed 2026-07-10.</p>
</body></html>
"""


def test_cross_link_requires_seed_handle_and_email_on_same_evidence():
    profile = IdentityProfile(username="RareHandle99", email="rarehandle99@example.com")
    art = artifact_from_http(source_url="https://one.example/r", body=REVIEW, status=200)
    handle = Entity(
        type=EntityType.HANDLE,
        original_value="RareHandle99",
        normalized_value="rarehandle99",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[art.evidence_id],
        confidence=0.8,
    )
    email = Entity(
        type=EntityType.EMAIL,
        original_value="rarehandle99@example.com",
        normalized_value="rarehandle99@example.com",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[art.evidence_id],
        confidence=0.85,
    )
    linked = detect_cross_linked_entity_ids(profile, [handle, email])
    assert handle.id in linked and email.id in linked

    hyps = build_identity_hypotheses(
        profile,
        [handle, email],
        independent_by_entity={handle.id: 1, email.id: 1},
        cross_linked_ids=linked,
    )
    by_type = {h.candidate_entity_id: h for h in hyps}
    assert "cross-link" in " ".join(by_type[handle.id].reasons).lower()
    assert by_type[handle.id].confidence > 0.45


def test_cross_link_absent_without_matching_email_seed():
    profile = IdentityProfile(username="RareHandle99")  # no email seed
    art = artifact_from_http(source_url="https://one.example/r", body=REVIEW, status=200)
    handle = Entity(
        type=EntityType.HANDLE,
        original_value="RareHandle99",
        normalized_value="rarehandle99",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[art.evidence_id],
    )
    email = Entity(
        type=EntityType.EMAIL,
        original_value="rarehandle99@example.com",
        normalized_value="rarehandle99@example.com",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[art.evidence_id],
    )
    assert detect_cross_linked_entity_ids(profile, [handle, email]) == set()


def test_page_claimed_other_author_is_contradicted():
    profile = IdentityProfile(username="RareHandle99")
    art = artifact_from_http(source_url="https://one.example/r", body=OTHER_AUTHOR, status=200)
    other = Entity(
        type=EntityType.HANDLE,
        original_value="OtherPerson42",
        normalized_value="otherperson42",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[art.evidence_id],
        attributes={"authorship": "page_claimed"},
    )
    contra = detect_contradicting_evidence(profile, [other])
    assert other.id in contra
    hyp = evaluate_handle_hypothesis(
        profile,
        other,
        contradicting=True,
        contradicting_evidence_ids=contra[other.id],
    )
    assert hyp.status == HypothesisStatus.CONTRADICTED
    assert hyp.contradicting_evidence_ids


def test_travel_confidence_by_author_hypothesis_status():
    art = artifact_from_http(source_url="https://travel.example/r", body=REVIEW, status=200)
    profile = IdentityProfile(username="RareHandle99")
    author = Entity(
        type=EntityType.HANDLE,
        original_value="RareHandle99",
        normalized_value="rarehandle99",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[art.evidence_id],
        attributes={"authorship": "page_claimed"},
    )

    cases = [
        (HypothesisStatus.LIKELY, True),
        (HypothesisStatus.POSSIBLE, False),
        (HypothesisStatus.CONTRADICTED, False),
    ]
    for status, expect_likely_label in cases:
        hyp = evaluate_handle_hypothesis(profile, author, independent_sources=2, cross_linked=True)
        hyp.status = status
        if status == HypothesisStatus.CONTRADICTED:
            hyp.confidence = 0.15
        events = extract_travel_events(art, author_hypothesis=hyp, is_mirror=False)
        assert events
        label = events[0].attributes.get("travel_confidence_label")
        if expect_likely_label:
            assert label == "likely" or events[0].confidence >= 0.55
        else:
            assert events[0].confidence < 0.7 or label == "possible"
        if status == HypothesisStatus.CONTRADICTED:
            assert "contradicted" in events[0].derivation_reason.lower()
            assert events[0].confidence <= 0.25


def test_mirror_lineage_passed_and_not_emitted_twice():
    findings = [
        Finding(platform="Web", title="Original", url="https://one.example/r", raw={"page_text": REVIEW}),
        Finding(platform="Web", title="Mirror", url="https://mirror.example/r", raw={"page_text": REVIEW}),
    ]
    payload = analyze_finding_pages(
        IdentityProfile(username="RareHandle99", email="rarehandle99@example.com"),
        findings,
        scan_id="corr",
        execute_queries=False,
    )
    travel = [e for e in payload["bundle"]["events"] if e["type"] == "travel"]
    assert len(travel) == 1
    assert "Author identity" in travel[0]["derivation_reason"]
    hyps = payload["hypotheses"]
    assert hyps
    # Cross-link from handle+email on same page should appear when email seed set.
    assert any("cross-link" in " ".join(h.get("reasons") or []).lower() for h in hyps)


def test_three_independent_sources_vs_mirrors():
    body_a = REVIEW + " Independent page A."
    body_b = REVIEW.replace("Lisbon", "Porto") + " Independent page B."
    body_c = REVIEW.replace("Aurora", "Borel") + " Independent page C."
    arts = [
        artifact_from_http(source_url="https://a.example/r", body=body_a, status=200),
        artifact_from_http(source_url="https://b.example/r", body=body_b, status=200),
        artifact_from_http(source_url="https://c.example/r", body=body_c, status=200),
        artifact_from_http(source_url="https://mirror.example/r", body=body_a, status=200),
    ]
    # Force mirror fingerprint
    arts[3].content_hash = arts[0].content_hash
    clusters = cluster_artifacts(arts)
    lineage = EvidenceLineageIndex.build(arts, clusters)
    entities = coalesce_identity_entities(
        [
            Entity(
                type=EntityType.HANDLE,
                original_value="RareHandle99",
                normalized_value="rarehandle99",
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[a.evidence_id],
            )
            for a in arts
        ]
    )
    from app.services.evidence_lineage import independent_sources_by_entity

    counts = independent_sources_by_entity(entities, lineage)
    assert list(counts.values()) == [3]
    hyp = build_identity_hypotheses(
        IdentityProfile(username="RareHandle99"),
        entities,
        independent_by_entity=counts,
    )[0]
    assert "3 independent" in " ".join(hyp.reasons) or hyp.confidence >= 0.55
