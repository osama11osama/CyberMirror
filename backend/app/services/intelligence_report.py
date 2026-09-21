"""Evidence-backed intelligence report summary (#50 / #65)."""

from __future__ import annotations

from html import escape


def build_intelligence_summary(intel: dict) -> dict:
    """Machine-readable report sections from an intelligence payload."""
    hyps = intel.get("hypotheses") or []
    events = (intel.get("bundle") or {}).get("events") or []
    clusters = intel.get("clusters") or []
    timeline = intel.get("timeline") or {}
    journal = intel.get("journal") or {}
    artifacts = intel.get("artifacts") or []

    identity = []
    for h in hyps:
        evidence_ids = h.get("supporting_evidence_ids") or []
        # Approximate independent count from clusters when available.
        independent = 1
        for cluster in clusters:
            members = set(cluster.get("member_artifact_ids") or [])
            # Evidence IDs map via artifacts.
            art_evidence = {
                a.get("evidence_id"): a.get("id")
                for a in artifacts
                if a.get("evidence_id")
            }
            matched = {
                art_evidence[eid]
                for eid in evidence_ids
                if eid in art_evidence and art_evidence[eid] in members
            }
            if matched:
                independent = max(independent, int(cluster.get("independent_source_count") or 1))
        identity.append(
            {
                "candidate": h.get("candidate_value"),
                "status": h.get("status"),
                "confidence": h.get("confidence"),
                "reasons": h.get("reasons") or [],
                "evidence_ids": evidence_ids,
                "contradicting_evidence_ids": h.get("contradicting_evidence_ids") or [],
                "hypothesis_id": h.get("id"),
                "independent_sources": independent,
                "journal_ref": f"identity-conclusion:{h.get('id')}",
            }
        )

    activity = []
    for e in events:
        if e.get("type") not in (
            "forum_post",
            "comment",
            "review",
            "social_post",
            "repository_activity",
        ):
            continue
        start = e.get("start") or {}
        pub = e.get("publication") or {}
        activity.append(
            {
                "event_id": e.get("id"),
                "type": e.get("type"),
                "title": e.get("title"),
                "platform": e.get("platform"),
                "source_url": e.get("source_url"),
                "excerpt": (e.get("excerpt") or "")[:280],
                "confidence": e.get("confidence"),
                "date_precision": start.get("precision") or pub.get("precision") or "unknown",
                "date_label": start.get("raw_text") or pub.get("raw_text") or "",
                "evidence_ids": e.get("supporting_evidence_ids") or [],
                "journal_ref": f"event:{e.get('id')}",
            }
        )

    travel = []
    for e in events:
        if e.get("type") != "travel":
            continue
        start = e.get("start") or {}
        pub = e.get("publication") or {}
        attrs = e.get("attributes") or {}
        travel.append(
            {
                "event_id": e.get("id"),
                "title": e.get("title"),
                "stay_raw": start.get("raw_text") or "",
                "stay_precision": start.get("precision") or "unknown",
                "publication_raw": pub.get("raw_text") or "",
                "publication_precision": pub.get("precision") or "unknown",
                "location": e.get("location_text") or "",
                "location_reason": e.get("location_reason") or "",
                "nights": attrs.get("nights"),
                "traveler_type": attrs.get("traveler_type"),
                "confidence": e.get("confidence"),
                "confidence_label": attrs.get("travel_confidence_label"),
                "derivation_reason": e.get("derivation_reason") or "",
                "evidence_ids": e.get("supporting_evidence_ids") or [],
                "lineage": attrs.get("lineage") or "original",
                "journal_ref": f"travel-conclusion:{e.get('id')}",
            }
        )

    blocked = [
        a
        for a in artifacts
        if (a.get("acquisition_method") in ("blocked", "error", "unsupported"))
        or a.get("blocked_reason")
    ]
    source_quality = {
        "clusters": len(clusters),
        "independent_observations": sum(int(c.get("independent_source_count") or 1) for c in clusters),
        "mirror_members": sum(int(c.get("mirror_count") or 0) for c in clusters),
        "blocked_acquisitions": len(blocked),
        "lineage": [
            {
                "id": c.get("id"),
                "lineage_type": c.get("lineage_type"),
                "reason": c.get("reason"),
                "independent": c.get("independent_source_count"),
                "mirrors": c.get("mirror_count"),
                "canonical_artifact_id": c.get("canonical_artifact_id"),
            }
            for c in clusters
        ],
    }

    dated = timeline.get("dated") or []
    unknown = timeline.get("unknown_date") or []
    condensed_timeline = {
        "dated": [
            {
                "event_id": e.get("event_id"),
                "event_type": e.get("event_type"),
                "date_label": e.get("date_label"),
                "precision": e.get("precision"),
                "description": e.get("description"),
                "verification_label": e.get("verification_label"),
                "independent_observations": e.get("independent_observations"),
                "hypothesis_id": e.get("hypothesis_id"),
                "evidence_ids": e.get("evidence_ids") or [],
            }
            for e in dated[:40]
        ],
        "unknown_date": [
            {
                "event_id": e.get("event_id"),
                "event_type": e.get("event_type"),
                "description": e.get("description"),
                "verification_label": e.get("verification_label"),
            }
            for e in unknown[:20]
        ],
    }

    conclusions = [
        s
        for s in (journal.get("steps") or [])
        if s.get("step_type") == "conclusion"
    ]

    return {
        "identity_summary": identity,
        "public_activity": activity,
        "travel_exposure": travel,
        "timeline": condensed_timeline,
        "source_quality": source_quality,
        "explainability": {
            "journal_step_count": len(journal.get("steps") or []),
            "conclusion_refs": [
                {
                    "step_id": c.get("id"),
                    "reason": c.get("reason"),
                    "output_refs": c.get("output_refs") or [],
                    "input_refs": c.get("input_refs") or [],
                }
                for c in conclusions[:30]
            ],
        },
        "journal_step_count": len(journal.get("steps") or []),
        "disclaimer": (
            "Identity hypotheses are not factual identity assertions. "
            "Possible/unresolved candidates must not be treated as confirmed ownership. "
            "Stay dates are distinct from review/publication dates."
        ),
    }


def intelligence_html_section(intel: dict) -> str:
    summary = build_intelligence_summary(intel)
    parts = [
        "<section class='intelligence-report'>",
        "<h2>Deep Intelligence Summary</h2>",
        f"<p>{escape(summary['disclaimer'])}</p>",
        "<h3>Identity hypotheses</h3><ul>",
    ]
    for h in summary["identity_summary"]:
        parts.append(
            "<li>"
            f"<strong>{escape(str(h.get('candidate') or ''))}</strong> — "
            f"status={escape(str(h.get('status')))} "
            f"(not a factual ownership claim); "
            f"confidence={escape(str(h.get('confidence')))}; "
            f"independent_sources={escape(str(h.get('independent_sources')))}; "
            f"hypothesis_id={escape(str(h.get('hypothesis_id') or ''))}; "
            f"journal_ref={escape(str(h.get('journal_ref') or ''))}. "
            f"{escape('; '.join(h.get('reasons') or []))}"
            "</li>"
        )
    if not summary["identity_summary"]:
        parts.append("<li>No identity hypotheses.</li>")

    parts.append("</ul><h3>Public activity</h3><ul>")
    for a in summary["public_activity"]:
        parts.append(
            "<li>"
            f"{escape(str(a.get('type') or ''))}: "
            f"{escape(str(a.get('title') or ''))} "
            f"platform={escape(str(a.get('platform') or ''))}; "
            f"date={escape(str(a.get('date_label') or 'unknown'))} "
            f"precision={escape(str(a.get('date_precision') or 'unknown'))}; "
            f"event_id={escape(str(a.get('event_id') or ''))}."
            f"<div>{escape(str(a.get('excerpt') or ''))}</div>"
            "</li>"
        )
    if not summary["public_activity"]:
        parts.append("<li>No public activity events extracted.</li>")

    parts.append("</ul><h3>Travel / location exposure</h3><ul>")
    for t in summary["travel_exposure"]:
        parts.append(
            "<li>"
            f"{escape(str(t.get('title') or 'Travel'))}: "
            f"stay={escape(str(t.get('stay_raw') or 'unknown'))} "
            f"precision={escape(str(t.get('stay_precision') or 'unknown'))}; "
            f"publication={escape(str(t.get('publication_raw') or 'unknown'))} "
            f"precision={escape(str(t.get('publication_precision') or 'unknown'))}; "
            f"location={escape(str(t.get('location') or 'unknown'))}; "
            f"confidence={escape(str(t.get('confidence')))} "
            f"label={escape(str(t.get('confidence_label') or ''))}; "
            f"journal_ref={escape(str(t.get('journal_ref') or ''))}. "
            f"{escape(str(t.get('derivation_reason') or ''))}"
            "</li>"
        )
    if not summary["travel_exposure"]:
        parts.append("<li>No travel events extracted.</li>")

    parts.append("</ul><h3>Timeline</h3><ul>")
    for e in (summary["timeline"].get("dated") or [])[:20]:
        parts.append(
            "<li>"
            f"{escape(str(e.get('date_label') or ''))} "
            f"({escape(str(e.get('precision') or ''))}) — "
            f"{escape(str(e.get('event_type') or ''))}: "
            f"{escape(str(e.get('description') or ''))}"
            "</li>"
        )
    for e in summary["timeline"].get("unknown_date") or []:
        parts.append(
            "<li>Unknown date — "
            f"{escape(str(e.get('event_type') or ''))}: "
            f"{escape(str(e.get('description') or ''))}"
            "</li>"
        )
    if not (summary["timeline"].get("dated") or summary["timeline"].get("unknown_date")):
        parts.append("<li>No timeline entries.</li>")

    parts.append("</ul><h3>Source quality</h3>")
    sq = summary["source_quality"]
    parts.append(
        "<p>"
        f"Clusters={sq['clusters']}, independent={sq['independent_observations']}, "
        f"mirror members={sq['mirror_members']}, "
        f"blocked acquisitions={sq['blocked_acquisitions']}."
        "</p>"
    )
    parts.append("<h3>Explainability</h3><ul>")
    for c in summary["explainability"]["conclusion_refs"][:15]:
        parts.append(
            "<li>"
            f"conclusion_id={escape(str(c.get('step_id') or ''))}: "
            f"{escape(str(c.get('reason') or ''))}"
            "</li>"
        )
    if not summary["explainability"]["conclusion_refs"]:
        parts.append("<li>No conclusion steps recorded.</li>")
    parts.append("</ul></section>")
    return "\n".join(parts)
