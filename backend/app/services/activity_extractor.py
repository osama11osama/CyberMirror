"""Authored activity extraction: forum posts, comments, reviews (#39)."""

from __future__ import annotations

import re

from app.models.intelligence import (
    Entity,
    EntityType,
    Event,
    EventType,
    IntelligenceOrigin,
    normalize_handle,
    parse_fuzzy_date,
)
from app.services.entity_extractor import extract_entities
from app.services.page_analyzer import PageArtifact

_AUTHOR_RE = re.compile(
    r"(?:posted by|author|reviewer|by)\s*:?\s*@?([A-Za-z0-9_\-.]{2,40})",
    re.I,
)
_REVIEW_MARKERS = ("review", "rated", "stayed", "traveller", "traveler", "nights")
_FORUM_MARKERS = ("forum", "thread", "replied", "post #", "topic:")
_COMMENT_MARKERS = ("comment", "replied to", "left a comment")
_STAY_RE = re.compile(
    r"stayed\s+(?:in\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
    re.I,
)
_RATING_RE = re.compile(r"(?:rated|rating|score)\s*[:=]?\s*(\d(?:\.\d)?)\s*(?:/\s*5)?", re.I)
_NIGHTS_RE = re.compile(r"(\d+)\s+nights?", re.I)
_TRAVELER_RE = re.compile(r"\b(solo|couple|family|business|friends|leisure)\b", re.I)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _infer_activity_type(text: str) -> EventType:
    low = text.lower()
    if any(m in low for m in _REVIEW_MARKERS):
        return EventType.REVIEW
    if any(m in low for m in _COMMENT_MARKERS):
        return EventType.COMMENT
    if any(m in low for m in _FORUM_MARKERS):
        return EventType.FORUM_POST
    return EventType.OTHER


def extract_activities(artifact: PageArtifact) -> tuple[list[Entity], list[Event]]:
    """Convert page content into activity events without asserting identity ownership."""
    if artifact.acquisition_method.value in ("blocked", "error", "unsupported"):
        return [], []

    text = f"{artifact.title}\n{artifact.main_text}"
    entities = extract_entities(artifact)
    etype = _infer_activity_type(text)
    if etype == EventType.OTHER and not artifact.title:
        return entities, []

    author_entity: Entity | None = None
    m = _AUTHOR_RE.search(text)
    if m:
        handle = m.group(1)
        author_entity = Entity(
            type=EntityType.HANDLE,
            original_value=handle,
            normalized_value=normalize_handle(handle),
            origin=IntelligenceOrigin.OBSERVED,
            supporting_evidence_ids=[artifact.evidence_id] if artifact.evidence_id else [],
            extraction_method="activity_author_byline",
            supporting_context="Page-level authorship observation only",
            confidence=0.7,
            scan_id=artifact.scan_id,
            attributes={"authorship": "page_claimed", "not_identity_proof": True},
        )
        entities.append(author_entity)

    attrs: dict = {}
    rating = _RATING_RE.search(text)
    if rating:
        attrs["rating"] = rating.group(1)
    nights = _NIGHTS_RE.search(text)
    if nights:
        attrs["nights"] = int(nights.group(1))
    traveler = _TRAVELER_RE.search(text)
    if traveler:
        attrs["traveler_type"] = traveler.group(1).lower()

    stay = _STAY_RE.search(text)
    start = parse_fuzzy_date()
    if stay:
        start = parse_fuzzy_date(
            stay.group(0),
            year=int(stay.group(2)),
            month=_MONTHS[stay.group(1).lower()],
        )

    # Publication date only when ISO-like present; never copy stay into publication.
    pub = parse_fuzzy_date()
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        pub = parse_fuzzy_date(
            iso.group(0),
            year=int(iso.group(1)),
            month=int(iso.group(2)),
            day=int(iso.group(3)),
        )

    related = [e.id for e in entities[:8]]
    event = Event(
        type=etype,
        title=(artifact.title or etype.value.replace("_", " ").title())[:120],
        description="",
        start=start,
        publication=pub,
        related_entity_ids=related,
        attributes=attrs,
        supporting_evidence_ids=[artifact.evidence_id] if artifact.evidence_id else [],
        confidence=0.55 if artifact.acquisition_method.value == "search_snippet" else 0.7,
        origin=IntelligenceOrigin.OBSERVED,
        derivation_reason="Authored activity metadata from public page (not identity ownership)",
        platform=artifact.metadata.get("platform", ""),
        source_url=artifact.final_url or artifact.source_url,
        excerpt=(artifact.main_text or "")[:280],
        scan_id=artifact.scan_id,
    )
    return entities, [event]
