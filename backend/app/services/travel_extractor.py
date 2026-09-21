"""Travel event reconstruction from accommodation/review evidence (#46)."""

from __future__ import annotations

import re

from app.models.intelligence import (
    DatePrecision,
    Entity,
    EntityType,
    Event,
    EventType,
    IntelligenceOrigin,
    parse_fuzzy_date,
)
from app.services.identity_hypotheses import HypothesisStatus, IdentityHypothesis
from app.services.page_analyzer import PageArtifact

_STAY_RE = re.compile(
    r"stayed\s+(?:in\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
    re.I,
)
_STAY_DAY_RE = re.compile(
    r"stayed\s+(?:on\s+)?(20\d{2})-(\d{2})-(\d{2})",
    re.I,
)
_PROPERTY_RE = re.compile(
    r"(?:hotel|hostel|apartment|resort|property)\s*:?\s*([A-Z][^.\n]{2,60})",
    re.I,
)
_CITY_RE = re.compile(r"\bin ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b")
_NIGHTS_RE = re.compile(r"(\d+)\s+nights?", re.I)
_TRAVELER_RE = re.compile(r"\b(solo|couple|family|business|friends|leisure)\b", re.I)
_RATING_RE = re.compile(r"(?:rated|rating|score)\s*[:=]?\s*(\d(?:\.\d)?)", re.I)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_travel_events(
    artifact: PageArtifact,
    *,
    author_hypothesis: IdentityHypothesis | None = None,
    is_mirror: bool = False,
    location_entities: list[Entity] | None = None,
) -> list[Event]:
    text = f"{artifact.title}\n{artifact.main_text}"
    low = text.lower()
    if not any(k in low for k in ("stayed", "hotel", "review", "accommodation", "hostel")):
        return []

    stay = parse_fuzzy_date()
    day = _STAY_DAY_RE.search(text)
    month = _STAY_RE.search(text)
    if day:
        stay = parse_fuzzy_date(
            day.group(0),
            year=int(day.group(1)),
            month=int(day.group(2)),
            day=int(day.group(3)),
        )
    elif month:
        stay = parse_fuzzy_date(
            month.group(0),
            year=int(month.group(2)),
            month=_MONTHS[month.group(1).lower()],
        )
    else:
        # Accommodation keywords alone are not enough — require an explicit stay date.
        return []

    # Publication date separate — never copy stay into publication.
    pub = parse_fuzzy_date()
    iso = re.search(r"reviewed\s+(20\d{2})-(\d{2})-(\d{2})", text, re.I)
    if not iso:
        iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso and stay.precision != DatePrecision.UNKNOWN:
        # Only treat as publication if distinct from stay day raw or labeled reviewed.
        pub = parse_fuzzy_date(
            iso.group(0),
            year=int(iso.group(1)),
            month=int(iso.group(2)),
            day=int(iso.group(3)),
        )
        if stay.precision == DatePrecision.EXACT_DAY and stay.value and pub.value == stay.value:
            pub = parse_fuzzy_date()  # ambiguous — leave unknown rather than invent

    attrs: dict = {}
    prop = _PROPERTY_RE.search(text)
    if prop:
        attrs["property"] = prop.group(1).strip()
    nights = _NIGHTS_RE.search(text)
    if nights:
        attrs["nights"] = int(nights.group(1))
    traveler = _TRAVELER_RE.search(text)
    if traveler:
        attrs["traveler_type"] = traveler.group(1).lower()
    rating = _RATING_RE.search(text)
    if rating:
        attrs["rating"] = rating.group(1)
    if is_mirror:
        attrs["lineage"] = "mirror"

    location_text = ""
    location_reason = ""
    location_id = None
    if location_entities:
        loc = next((e for e in location_entities if e.type == EntityType.LOCATION), None)
        if loc:
            location_text = loc.original_value
            location_id = loc.id
            location_reason = "Location entity extracted from source metadata/text"
    if not location_text:
        city = _CITY_RE.search(text)
        if city:
            location_text = city.group(1)
            location_reason = "City mention in review text"

    conf = 0.4
    reasons = ["Accommodation/review language detected"]
    if stay.precision != DatePrecision.UNKNOWN:
        conf += 0.15
        reasons.append(f"Stay date precision={stay.precision.value}")
    if author_hypothesis:
        if author_hypothesis.status in (HypothesisStatus.VERIFIED, HypothesisStatus.LIKELY):
            conf += 0.2
            reasons.append(f"Author identity hypothesis={author_hypothesis.status.value}")
        elif author_hypothesis.status in (HypothesisStatus.POSSIBLE, HypothesisStatus.UNRESOLVED):
            conf += 0.05
            reasons.append("Author identity only possible/unresolved")
        elif author_hypothesis.status == HypothesisStatus.CONTRADICTED:
            conf = min(conf, 0.25)
            reasons.append("Author identity contradicted — travel remains low confidence")
    if is_mirror:
        conf -= 0.05
        reasons.append("Source is a mirror/duplicate — does not add independent corroboration")
    if artifact.acquisition_method.value == "search_snippet":
        conf -= 0.1
        reasons.append("Snippet-only acquisition is weaker than direct page")

    conf = max(0.1, min(0.85, conf))
    status_note = "possible"
    if conf >= 0.7 and author_hypothesis and author_hypothesis.status in (
        HypothesisStatus.VERIFIED,
        HypothesisStatus.LIKELY,
    ):
        status_note = "likely"
    attrs["travel_confidence_label"] = status_note

    return [
        Event(
            type=EventType.TRAVEL,
            title=attrs.get("property") or artifact.title or "Travel stay",
            start=stay,
            publication=pub,
            location_entity_id=location_id,
            location_text=location_text,
            location_reason=location_reason,
            attributes=attrs,
            supporting_evidence_ids=[artifact.evidence_id] if artifact.evidence_id else [],
            confidence=round(conf, 2),
            origin=IntelligenceOrigin.DERIVED,
            derivation_reason="; ".join(reasons),
            source_url=artifact.final_url or artifact.source_url,
            excerpt=(artifact.main_text or "")[:240],
            scan_id=artifact.scan_id,
            related_entity_ids=[location_id] if location_id else [],
        )
    ]
