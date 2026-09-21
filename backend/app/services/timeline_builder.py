"""Evidence-backed digital timeline (#47)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.intelligence import DatePrecision, Event, EventType, FuzzyDate
from app.services.evidence_clustering import EvidenceCluster
from app.services.identity_hypotheses import HypothesisStatus, IdentityHypothesis


class TimelineEntry(BaseModel):
    event_id: str
    event_type: str
    date_label: str
    precision: str
    sort_key: str
    platform: str = ""
    description: str = ""
    confidence: float = 0.0
    verification_label: str = "observed"
    location: str = ""
    entity_labels: list[str] = Field(default_factory=list)
    independent_observations: int = 1
    evidence_ids: list[str] = Field(default_factory=list)
    unknown_date: bool = False


def _date_label(fd: FuzzyDate) -> str:
    if fd.precision == DatePrecision.UNKNOWN or fd.value is None:
        return fd.raw_text or "Unknown date"
    if fd.precision == DatePrecision.YEAR:
        return f"{fd.value.year}"
    if fd.precision == DatePrecision.MONTH:
        return f"{fd.value.year}-{fd.value.month:02d}"
    if fd.precision == DatePrecision.EXACT_DAY:
        return fd.value.isoformat()
    if fd.datetime_value:
        return fd.datetime_value.isoformat()
    return fd.value.isoformat()


def build_timeline(
    events: list[Event],
    *,
    hypotheses: list[IdentityHypothesis] | None = None,
    clusters: list[EvidenceCluster] | None = None,
    event_types: set[str] | None = None,
    min_confidence: float = 0.0,
) -> tuple[list[TimelineEntry], list[TimelineEntry]]:
    """Return (dated_entries, unknown_date_entries)."""
    hyp_by_evidence: dict[str, IdentityHypothesis] = {}
    for h in hypotheses or []:
        for eid in h.supporting_evidence_ids:
            hyp_by_evidence[eid] = h

    # Map evidence → independent count via clusters.
    indep_by_evidence: dict[str, int] = {}
    for c in clusters or []:
        for mid in c.member_artifact_ids:
            indep_by_evidence[mid] = c.independent_source_count

    dated: list[TimelineEntry] = []
    unknown: list[TimelineEntry] = []
    seen_fp: set[str] = set()

    for ev in events:
        if event_types and ev.type.value not in event_types:
            continue
        if ev.confidence < min_confidence:
            continue
        # Deduplicate travel/activity that share same evidence+type+start.
        fp = f"{ev.type.value}|{ev.start.raw_text}|{','.join(ev.supporting_evidence_ids)}"
        if fp in seen_fp:
            continue
        seen_fp.add(fp)

        # Prefer stay/start date; fall back to publication for activity chronology.
        primary = ev.start
        if primary.precision == DatePrecision.UNKNOWN:
            primary = ev.publication

        label = "derived" if ev.origin.value == "derived" else "observed"
        for eid in ev.supporting_evidence_ids:
            h = hyp_by_evidence.get(eid)
            if h:
                if h.status in (HypothesisStatus.VERIFIED, HypothesisStatus.LIKELY):
                    label = h.status.value
                elif h.status in (HypothesisStatus.POSSIBLE, HypothesisStatus.UNRESOLVED):
                    label = h.status.value
                break

        indep = 1
        for eid in ev.supporting_evidence_ids:
            indep = max(indep, indep_by_evidence.get(eid, 1))

        entry = TimelineEntry(
            event_id=ev.id,
            event_type=ev.type.value,
            date_label=_date_label(primary),
            precision=primary.precision.value,
            sort_key=f"{primary.sort_key()[0]}|{primary.sort_key()[1]}|{ev.id}",
            platform=ev.platform,
            description=(ev.title or ev.excerpt)[:160],
            confidence=ev.confidence,
            verification_label=label,
            location=ev.location_text,
            evidence_ids=list(ev.supporting_evidence_ids),
            independent_observations=indep,
            unknown_date=primary.precision == DatePrecision.UNKNOWN,
        )
        if entry.unknown_date:
            unknown.append(entry)
        else:
            dated.append(entry)

    dated.sort(key=lambda e: e.sort_key)
    return dated, unknown
