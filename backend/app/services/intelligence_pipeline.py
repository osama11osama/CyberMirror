"""Deep intelligence pipeline orchestrator (v2.5)."""

from __future__ import annotations

import asyncio
import threading

from app.config import settings
from app.models.intelligence import (
    Entity,
    Event,
    IntelligenceBundle,
    seed_entities_from_profile,
)
from app.models.schemas import Finding, IdentityProfile
from app.services.activity_extractor import extract_activities
from app.services.evidence_clustering import cluster_artifacts
from app.services.evidence_lineage import EvidenceLineageIndex, independent_sources_by_entity
from app.services.identity_hypotheses import build_identity_hypotheses
from app.services.investigation_budget import InvestigationBudget, default_budget, get_budget
from app.services.investigation_journal import (
    InvestigationJournal,
    JournalStep,
    JournalStepType,
)
from app.services.page_analyzer import (
    AcquisitionMethod,
    PageArtifact,
    acquire_page,
    artifact_from_http,
)
from app.services.query_planner import build_investigation_plan
from app.services.timeline_builder import build_timeline
from app.services.travel_extractor import extract_travel_events


async def analyze_finding_pages_async(
    profile: IdentityProfile,
    findings: list[Finding],
    *,
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
    max_pages: int = 12,
) -> dict:
    """Analyze findings, acquiring eligible public URLs when content is absent."""
    budget = budget or get_budget(scan_id) or default_budget(scan_id)
    journal = InvestigationJournal(scan_id=scan_id)
    seed_ents = seed_entities_from_profile(profile, scan_id=scan_id)
    seed_step = journal.add(
        JournalStep(
            step_type=JournalStepType.SEED,
            reason="Investigator seed identifiers recorded",
            output_refs=[e.id for e in seed_ents],
            metadata={"count": len(seed_ents)},
        )
    )

    plan = build_investigation_plan(profile)
    for pq in plan[:8]:
        journal.add(
            JournalStep(
                parent_ids=[seed_step.id],
                step_type=JournalStepType.QUERY,
                reason=pq.reason,
                output_refs=[pq.id],
                metadata={
                    "query": pq.query,
                    "family": pq.family.value,
                    "state": "planned",
                },
            )
        )

    artifacts: list[PageArtifact] = []
    entities: list[Entity] = list(seed_ents)
    events: list[Event] = []
    entities_by_artifact: dict[str, list[Entity]] = {}
    acquisition_step_by_artifact: dict[str, str] = {}

    candidates = [
        f
        for f in findings
        if f.url and f.platform not in ("Summary", "System", "Correlation Engine")
    ][:max_pages]

    for f in candidates:
        stop = budget.check_continue()
        if stop or budget.is_cancelled():
            journal.add(
                JournalStep(
                    step_type=JournalStepType.BLOCKED,
                    reason=stop or "cancelled",
                    status="stopped",
                )
            )
            break

        result_step = journal.add(
            JournalStep(
                parent_ids=[seed_step.id],
                step_type=JournalStepType.SEARCH_RESULT,
                reason="Public search result selected for deep analysis",
                input_refs=[f.id],
                output_refs=[f.id],
                metadata={"url": f.url, "platform": f.platform},
            )
        )

        raw_body = ""
        if isinstance(f.raw, dict):
            raw_body = str(f.raw.get("page_text") or f.raw.get("body") or "")
        snippet = f.snippet or f.description or ""

        if raw_body:
            if budget.consume_page(f.url):
                break
            art = artifact_from_http(
                source_url=f.url,
                body=raw_body,
                status=200,
                title=f.title,
                scan_id=scan_id,
                budget=budget,
            )
        else:
            art = await acquire_page(
                f.url,
                scan_id=scan_id,
                budget=budget,
                prefer_playwright=settings.playwright_enabled,
                snippet_fallback=snippet,
                title=f.title,
            )

        artifacts.append(art)
        art.metadata.setdefault("platform", f.platform)
        parent = journal.add(
            JournalStep(
                parent_ids=[result_step.id],
                step_type=JournalStepType.ACQUISITION
                if art.acquisition_method
                not in (AcquisitionMethod.BLOCKED, AcquisitionMethod.ERROR, AcquisitionMethod.UNSUPPORTED)
                else JournalStepType.BLOCKED,
                reason=f"Acquire {art.acquisition_method.value}",
                input_refs=[f.id],
                output_refs=[art.id],
                metadata={"url": f.url, "method": art.acquisition_method.value},
                status="ok" if not art.blocked_reason else "blocked",
            )
        )
        acquisition_step_by_artifact[art.id] = parent.id

        destination_failure = art.metadata.get("destination_failure_reason")
        if destination_failure:
            journal.add(
                JournalStep(
                    parent_ids=[parent.id],
                    step_type=JournalStepType.BLOCKED,
                    reason=str(destination_failure),
                    input_refs=[f.id],
                    output_refs=[art.id],
                    metadata={"fallback": "search_snippet"},
                    status="fallback",
                )
            )

        if art.blocked_reason:
            continue

        ents, acts = extract_activities(art)
        entities_by_artifact[art.id] = ents
        entities.extend(ents)
        events.extend(acts)
        entity_step = journal.add(
            JournalStep(
                parent_ids=[parent.id],
                step_type=JournalStepType.ENTITY_EXTRACTION,
                reason="Extract structured entities",
                input_refs=[art.id, art.evidence_id],
                output_refs=[e.id for e in ents],
                metadata={"count": len(ents)},
            )
        )
        journal.add(
            JournalStep(
                parent_ids=[entity_step.id],
                step_type=JournalStepType.ACTIVITY_EXTRACTION,
                reason="Extract authored activity",
                input_refs=[art.id],
                output_refs=[e.id for e in ents] + [a.id for a in acts],
            )
        )

    clusters = cluster_artifacts(artifacts)
    cluster_step_by_id: dict[str, str] = {}
    for cluster in clusters:
        cluster_step = journal.add(
            JournalStep(
                parent_ids=[
                    acquisition_step_by_artifact[artifact_id]
                    for artifact_id in cluster.member_artifact_ids
                    if artifact_id in acquisition_step_by_artifact
                ],
                step_type=JournalStepType.CLUSTER,
                reason=cluster.reason,
                output_refs=[cluster.id],
                metadata={
                    "independent": cluster.independent_source_count,
                    "mirrors": cluster.mirror_count,
                    "lineage": cluster.lineage_type.value,
                },
            )
        )
        cluster_step_by_id[cluster.id] = cluster_step.id

    # Translate evidence -> artifact -> cluster before calculating identity
    # corroboration.  Mirrors therefore contribute one observation.
    observed = [e for e in entities if e.origin.value != "seed"]
    lineage = EvidenceLineageIndex.build(artifacts, clusters)
    hypotheses = build_identity_hypotheses(
        profile,
        observed,
        independent_by_entity=independent_sources_by_entity(observed, lineage),
    )
    identity_step_by_entity: dict[str, str] = {}
    for hypothesis in hypotheses:
        parent_cluster_steps = {
            cluster_step_by_id[cluster_id]
            for evidence_id in hypothesis.supporting_evidence_ids
            if (cluster_id := lineage.cluster_id_for_evidence(evidence_id))
            in cluster_step_by_id
        }
        identity_step = journal.add(
            JournalStep(
                parent_ids=sorted(parent_cluster_steps),
                step_type=JournalStepType.IDENTITY,
                reason="; ".join(hypothesis.reasons),
                output_refs=[hypothesis.id],
                input_refs=hypothesis.supporting_evidence_ids,
                metadata={
                    "status": hypothesis.status.value,
                    "confidence": hypothesis.confidence,
                },
            )
        )
        identity_step_by_entity[hypothesis.candidate_entity_id] = identity_step.id
        journal.add(
            JournalStep(
                parent_ids=[identity_step.id],
                step_type=JournalStepType.CONCLUSION,
                reason=f"Account ownership remains {hypothesis.status.value}",
                input_refs=[hypothesis.id] + hypothesis.supporting_evidence_ids,
                output_refs=[f"identity-conclusion:{hypothesis.id}"],
                metadata={
                    "status": hypothesis.status.value,
                    "confidence": hypothesis.confidence,
                },
            )
        )

    # Travel is derived only after author identity and mirror lineage are known.
    # Mirror copies are skipped rather than emitted as duplicate travel claims.
    hypotheses_by_entity = {h.candidate_entity_id: h for h in hypotheses}
    for artifact in artifacts:
        if artifact.blocked_reason or lineage.is_mirror_artifact(artifact.id):
            continue
        artifact_entities = entities_by_artifact.get(artifact.id, [])
        author = next(
            (
                entity
                for entity in artifact_entities
                if entity.attributes.get("authorship") == "page_claimed"
            ),
            None,
        )
        author_hypothesis = hypotheses_by_entity.get(author.id) if author else None
        travels = extract_travel_events(
            artifact,
            author_hypothesis=author_hypothesis,
            location_entities=[e for e in artifact_entities if e.type.value == "location"],
        )
        events.extend(travels)
        for travel in travels:
            parents = [acquisition_step_by_artifact.get(artifact.id, "")]
            if author and author.id in identity_step_by_entity:
                parents.append(identity_step_by_entity[author.id])
            event_step = journal.add(
                JournalStep(
                    parent_ids=[parent for parent in parents if parent],
                    step_type=JournalStepType.EVENT,
                    reason=travel.derivation_reason,
                    input_refs=[artifact.id, artifact.evidence_id]
                    + ([author_hypothesis.id] if author_hypothesis else []),
                    output_refs=[travel.id],
                    metadata={"event_type": travel.type.value},
                )
            )
            journal.add(
                JournalStep(
                    parent_ids=[event_step.id],
                    step_type=JournalStepType.CONCLUSION,
                    reason=(
                        "Travel attribution remains "
                        f"{travel.attributes.get('travel_confidence_label', 'possible')}"
                    ),
                    input_refs=[travel.id] + travel.supporting_evidence_ids,
                    output_refs=[f"travel-conclusion:{travel.id}"],
                    metadata={"confidence": travel.confidence},
                )
            )

    dated, unknown = build_timeline(
        events,
        hypotheses=hypotheses,
        clusters=clusters,
        artifacts=artifacts,
    )
    bundle = IntelligenceBundle(entities=entities, events=events)

    return {
        "bundle": bundle.model_dump(mode="json"),
        "artifacts": [a.model_dump(mode="json") for a in artifacts],
        "clusters": [c.model_dump(mode="json") for c in clusters],
        "hypotheses": [h.model_dump(mode="json") for h in hypotheses],
        "timeline": {
            "dated": [e.model_dump(mode="json") for e in dated],
            "unknown_date": [e.model_dump(mode="json") for e in unknown],
        },
        "journal": journal.model_dump(mode="json"),
        "query_plan": [p.model_dump(mode="json") for p in plan],
        "budget": budget.as_dict(),
    }


def analyze_finding_pages(
    profile: IdentityProfile,
    findings: list[Finding],
    *,
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
    max_pages: int = 12,
) -> dict:
    """Synchronous compatibility wrapper for API threadpool and older callers."""
    coroutine = analyze_finding_pages_async(
        profile,
        findings,
        scan_id=scan_id,
        budget=budget,
        max_pages=max_pages,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: list[dict] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
