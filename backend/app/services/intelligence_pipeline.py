"""Deep intelligence pipeline orchestrator (v2.5)."""

from __future__ import annotations

from app.models.intelligence import (
    Entity,
    Event,
    IntelligenceBundle,
    seed_entities_from_profile,
)
from app.models.schemas import Finding, IdentityProfile
from app.services.activity_extractor import extract_activities
from app.services.evidence_clustering import cluster_artifacts
from app.services.identity_hypotheses import build_identity_hypotheses
from app.services.investigation_budget import InvestigationBudget, default_budget
from app.services.investigation_journal import (
    InvestigationJournal,
    JournalStep,
    JournalStepType,
)
from app.services.page_analyzer import (
    AcquisitionMethod,
    PageArtifact,
    artifact_from_http,
    artifact_from_snippet,
)
from app.services.query_planner import build_investigation_plan
from app.services.timeline_builder import build_timeline
from app.services.travel_extractor import extract_travel_events


def analyze_finding_pages(
    profile: IdentityProfile,
    findings: list[Finding],
    *,
    scan_id: str = "",
    budget: InvestigationBudget | None = None,
    max_pages: int = 12,
) -> dict:
    """Run deep analysis over strong URL findings using fixtures-friendly acquisition.

    Live HTTP is optional; when a finding has snippet/raw body, use offline path.
    """
    budget = budget or default_budget(scan_id)
    journal = InvestigationJournal(scan_id=scan_id)
    seed_ents = seed_entities_from_profile(profile, scan_id=scan_id)
    journal.add(
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
                step_type=JournalStepType.QUERY,
                reason=pq.reason,
                output_refs=[pq.id],
                metadata={"query": pq.query, "family": pq.family.value},
            )
        )

    artifacts: list[PageArtifact] = []
    entities: list[Entity] = list(seed_ents)
    events: list[Event] = []

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
        elif snippet:
            art = artifact_from_snippet(
                source_url=f.url, snippet=snippet, title=f.title, scan_id=scan_id
            )
        else:
            # No local body — record planned acquisition without live crawl in CI.
            art = PageArtifact(
                source_url=f.url,
                title=f.title,
                acquisition_method=AcquisitionMethod.UNSUPPORTED,
                blocked_reason="no_local_content_for_offline_analysis",
                scan_id=scan_id,
            )

        artifacts.append(art)
        parent = journal.add(
            JournalStep(
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

        if art.blocked_reason:
            continue

        ents, acts = extract_activities(art)
        entities.extend(ents)
        events.extend(acts)
        journal.add(
            JournalStep(
                parent_ids=[parent.id],
                step_type=JournalStepType.ACTIVITY_EXTRACTION,
                reason="Extract authored activity and entities",
                input_refs=[art.id],
                output_refs=[e.id for e in ents] + [a.id for a in acts],
            )
        )

        # Travel from review-like content.
        loc_ents = [e for e in ents if e.type.value == "location"]
        travels = extract_travel_events(art, location_entities=loc_ents)
        events.extend(travels)
        for tr in travels:
            journal.add(
                JournalStep(
                    parent_ids=[parent.id],
                    step_type=JournalStepType.EVENT,
                    reason=tr.derivation_reason,
                    input_refs=[art.id],
                    output_refs=[tr.id],
                    metadata={"event_type": tr.type.value},
                )
            )

    clusters = cluster_artifacts(artifacts)
    for c in clusters:
        journal.add(
            JournalStep(
                step_type=JournalStepType.CLUSTER,
                reason=c.reason,
                output_refs=[c.id],
                metadata={
                    "independent": c.independent_source_count,
                    "mirrors": c.mirror_count,
                    "lineage": c.lineage_type.value,
                },
            )
        )

    # Observed entities only for hypotheses.
    observed = [e for e in entities if e.origin.value != "seed"]
    hypotheses = build_identity_hypotheses(profile, observed)
    for h in hypotheses:
        journal.add(
            JournalStep(
                step_type=JournalStepType.IDENTITY,
                reason="; ".join(h.reasons),
                output_refs=[h.id],
                input_refs=h.supporting_evidence_ids,
                metadata={"status": h.status.value, "confidence": h.confidence},
            )
        )

    dated, unknown = build_timeline(events, hypotheses=hypotheses, clusters=clusters)
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
