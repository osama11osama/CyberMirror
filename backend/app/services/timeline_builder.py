"""Evidence-backed digital timeline (#47 / #63)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.models.intelligence import DatePrecision, Event, FuzzyDate
from app.services.evidence_clustering import EvidenceCluster
from app.services.evidence_lineage import EvidenceLineageIndex
from app.services.identity_hypotheses import HypothesisStatus, IdentityHypothesis
from app.services.page_analyzer import PageArtifact


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
    origin: str = "observed"
    hypothesis_id: str = ""
    hypothesis_status: str = ""
    source_url: str = ""
    cluster_ids: list[str] = Field(default_factory=list)


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
    artifacts: list[PageArtifact] | None = None,
    event_types: set[str] | None = None,
    min_confidence: float = 0.0,
) -> tuple[list[TimelineEntry], list[TimelineEntry]]:
    """Return (dated_entries, unknown_date_entries)."""
    hyp_by_evidence: dict[str, IdentityHypothesis] = {}
    for h in hypotheses or []:
        for eid in h.supporting_evidence_ids:
            hyp_by_evidence[eid] = h

    # Translate evidence -> artifact -> cluster explicitly.  These IDs are
    # distinct namespaces and must never be compared directly.
    lineage = EvidenceLineageIndex.build(artifacts or [], clusters or [])
    artifact_by_id = {a.id: a for a in (artifacts or [])}

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
        hyp_id = ""
        hyp_status = ""
        for eid in ev.supporting_evidence_ids:
            h = hyp_by_evidence.get(eid)
            if h:
                hyp_id = h.id
                hyp_status = h.status.value
                if h.status in (HypothesisStatus.VERIFIED, HypothesisStatus.LIKELY):
                    label = h.status.value
                elif h.status in (HypothesisStatus.POSSIBLE, HypothesisStatus.UNRESOLVED):
                    label = h.status.value
                break

        indep = lineage.independent_count(ev.supporting_evidence_ids)
        cluster_ids: list[str] = []
        source_url = ev.source_url or ""
        for evidence_id in ev.supporting_evidence_ids:
            cluster_id = lineage.cluster_id_for_evidence(evidence_id)
            if cluster_id and cluster_id not in cluster_ids:
                cluster_ids.append(cluster_id)
            artifact_id = lineage.artifact_by_evidence.get(evidence_id)
            artifact = artifact_by_id.get(artifact_id or "")
            if artifact and not source_url:
                source_url = artifact.final_url or artifact.source_url

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
            origin=ev.origin.value,
            hypothesis_id=hyp_id,
            hypothesis_status=hyp_status,
            source_url=source_url,
            cluster_ids=cluster_ids,
        )
        if entry.unknown_date:
            unknown.append(entry)
        else:
            dated.append(entry)

    dated.sort(key=lambda e: e.sort_key)
    return dated, unknown


def filter_timeline_entries(
    dated: list[TimelineEntry],
    unknown: list[TimelineEntry],
    *,
    event_type: str | None = None,
    platform: str | None = None,
    location: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    verification: str | None = None,
    origin: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[TimelineEntry], list[TimelineEntry]]:
    """Client/API helper filters for timeline navigation (#63)."""

    def _ok(entry: TimelineEntry) -> bool:
        if event_type and entry.event_type != event_type:
            return False
        if platform and platform.lower() not in (entry.platform or "").lower():
            return False
        if location and location.lower() not in (entry.location or "").lower():
            return False
        if min_confidence is not None and entry.confidence < min_confidence:
            return False
        if max_confidence is not None and entry.confidence > max_confidence:
            return False
        if verification and entry.verification_label != verification:
            return False
        if origin and entry.origin != origin:
            return False
        if date_from or date_to:
            if entry.unknown_date:
                return False
            # date_label for month is YYYY-MM; exact is YYYY-MM-DD; year is YYYY
            label = entry.date_label
            try:
                if entry.precision == DatePrecision.YEAR.value:
                    entry_date = date(int(label), 1, 1)
                elif entry.precision == DatePrecision.MONTH.value:
                    y, m = label.split("-")[:2]
                    entry_date = date(int(y), int(m), 1)
                else:
                    entry_date = date.fromisoformat(label[:10])
            except ValueError:
                return False
            if date_from and entry_date < date_from:
                return False
            if date_to and entry_date > date_to:
                return False
        return True

    return [e for e in dated if _ok(e)], [e for e in unknown if _ok(e)]
