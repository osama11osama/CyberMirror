"""Evidence-backed intelligence report summary (#50)."""

from __future__ import annotations

from html import escape


def build_intelligence_summary(intel: dict) -> dict:
    """Machine-readable report sections from an intelligence payload."""
    hyps = intel.get("hypotheses") or []
    events = (intel.get("bundle") or {}).get("events") or []
    clusters = intel.get("clusters") or []
    timeline = intel.get("timeline") or {}
    journal = intel.get("journal") or {}

    identity = [
        {
            "candidate": h.get("candidate_value"),
            "status": h.get("status"),
            "confidence": h.get("confidence"),
            "reasons": h.get("reasons") or [],
            "evidence_ids": h.get("supporting_evidence_ids") or [],
            "hypothesis_id": h.get("id"),
        }
        for h in hyps
    ]
    activity = [
        e
        for e in events
        if e.get("type") in ("forum_post", "comment", "review", "social_post", "repository_activity")
    ]
    travel = [e for e in events if e.get("type") == "travel"]
    source_quality = {
        "clusters": len(clusters),
        "independent_observations": sum(int(c.get("independent_source_count") or 1) for c in clusters),
        "mirror_members": sum(int(c.get("mirror_count") or 0) for c in clusters),
        "lineage": [
            {
                "id": c.get("id"),
                "lineage_type": c.get("lineage_type"),
                "reason": c.get("reason"),
                "independent": c.get("independent_source_count"),
                "mirrors": c.get("mirror_count"),
            }
            for c in clusters
        ],
    }
    return {
        "identity_summary": identity,
        "public_activity": activity,
        "travel_exposure": travel,
        "timeline": timeline,
        "source_quality": source_quality,
        "journal_step_count": len((journal.get("steps") or [])),
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
            f"confidence={escape(str(h.get('confidence')))}. "
            f"{escape('; '.join(h.get('reasons') or []))}"
            "</li>"
        )
    if not summary["identity_summary"]:
        parts.append("<li>No identity hypotheses.</li>")
    parts.append("</ul><h3>Travel / location exposure</h3><ul>")
    for t in summary["travel_exposure"]:
        start = (t.get("start") or {})
        parts.append(
            "<li>"
            f"{escape(str(t.get('title') or 'Travel'))}: "
            f"stay={escape(str(start.get('raw_text') or start.get('precision') or 'unknown'))} "
            f"precision={escape(str(start.get('precision') or 'unknown'))}; "
            f"location={escape(str(t.get('location_text') or 'unknown'))}; "
            f"confidence={escape(str(t.get('confidence')))} "
            f"({escape(str(t.get('origin') or 'derived'))})"
            "</li>"
        )
    if not summary["travel_exposure"]:
        parts.append("<li>No travel events extracted.</li>")
    parts.append("</ul><h3>Source quality</h3>")
    sq = summary["source_quality"]
    parts.append(
        "<p>"
        f"Clusters={sq['clusters']}, independent={sq['independent_observations']}, "
        f"mirror members={sq['mirror_members']}."
        "</p></section>"
    )
    return "\n".join(parts)
