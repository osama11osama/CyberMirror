"""Authored activity extraction: forum posts, comments, reviews (#39 / #61)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

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
    r"(?:posted by|author|reviewer|comment by|by)\s*:?\s*@?([A-Za-z0-9_\-.]{2,40})",
    re.I,
)
_DATE_LINE_RE = re.compile(
    r"(?:on|date|reviewed|posted)\s*:?\s*((?:20\d{2}-\d{2}-\d{2})|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})",
    re.I,
)
_REVIEW_MARKERS = ("review", "rated", "stayed", "traveller", "traveler", "nights")
_FORUM_MARKERS = ("forum", "thread", "replied", "post #", "topic:")
_COMMENT_MARKERS = ("comment", "replied to", "left a comment")
_REPO_MARKERS = ("github.com", "committed", "starred", "repository", "pull request", "opened issue")
_STAY_RE = re.compile(
    r"stayed\s+(?:in\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
    re.I,
)
_RATING_RE = re.compile(r"(?:rated|rating|score)\s*[:=]?\s*(\d(?:\.\d)?)\s*(?:/\s*5)?", re.I)
_NIGHTS_RE = re.compile(r"(\d+)\s+nights?", re.I)
_TRAVELER_RE = re.compile(r"\b(solo|couple|family|business|friends|leisure)\b", re.I)
_POST_SPLIT_RE = re.compile(
    r"(?=(?:^|\n)\s*(?:Posted by|Author|Reviewer|Comment by)\s*:)",
    re.I,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _infer_activity_type(text: str, *, source_url: str = "") -> EventType:
    low = text.lower()
    host = ""
    try:
        host = (urlparse(source_url).hostname or "").lower()
    except Exception:
        host = ""
    if "github.com" in host or any(m in low for m in _REPO_MARKERS if m != "github.com"):
        if any(k in low for k in ("commit", "starred", "pull request", "opened issue", "repository")):
            return EventType.REPOSITORY_ACTIVITY
    if any(m in low for m in _REVIEW_MARKERS):
        return EventType.REVIEW
    if any(m in low for m in _COMMENT_MARKERS):
        return EventType.COMMENT
    if any(m in low for m in _FORUM_MARKERS):
        return EventType.FORUM_POST
    return EventType.OTHER


def _parse_pub_date(text: str):
    pub = parse_fuzzy_date()
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        return parse_fuzzy_date(
            iso.group(0),
            year=int(iso.group(1)),
            month=int(iso.group(2)),
            day=int(iso.group(3)),
        )
    month = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        text,
        re.I,
    )
    if month:
        return parse_fuzzy_date(
            month.group(0),
            year=int(month.group(2)),
            month=_MONTHS[month.group(1).lower()],
        )
    return pub


def _split_authored_blocks(text: str) -> list[str]:
    """Split a page into authored blocks when multiple bylines are explicit."""
    parts = [p.strip() for p in _POST_SPLIT_RE.split(text or "") if p and p.strip()]
    if len(parts) <= 1:
        return [text]
    # Keep only blocks that themselves contain an author byline.
    authored = [p for p in parts if _AUTHOR_RE.search(p)]
    return authored if len(authored) >= 2 else [text]


def _event_from_block(
    artifact: PageArtifact,
    block: str,
    *,
    entities: list[Entity],
    index: int,
    total: int,
) -> tuple[Entity | None, Event]:
    etype = _infer_activity_type(block, source_url=artifact.source_url or artifact.final_url)
    author_entity: Entity | None = None
    m = _AUTHOR_RE.search(block)
    if m:
        handle = m.group(1)
        author_entity = Entity(
            type=EntityType.HANDLE,
            original_value=handle,
            normalized_value=normalize_handle(handle),
            origin=IntelligenceOrigin.OBSERVED,
            supporting_evidence_ids=[artifact.evidence_id] if artifact.evidence_id else [],
            extraction_method="activity_author_byline",
            supporting_context="Per-entry authorship observation only",
            confidence=0.7,
            scan_id=artifact.scan_id,
            attributes={
                "authorship": "page_claimed",
                "not_identity_proof": True,
                "block_index": index,
            },
        )

    attrs: dict = {"block_index": index, "block_count": total}
    rating = _RATING_RE.search(block)
    if rating:
        attrs["rating"] = rating.group(1)
    nights = _NIGHTS_RE.search(block)
    if nights:
        attrs["nights"] = int(nights.group(1))
    traveler = _TRAVELER_RE.search(block)
    if traveler:
        attrs["traveler_type"] = traveler.group(1).lower()

    stay = _STAY_RE.search(block)
    start = parse_fuzzy_date()
    if stay:
        start = parse_fuzzy_date(
            stay.group(0),
            year=int(stay.group(2)),
            month=_MONTHS[stay.group(1).lower()],
        )

    pub = _parse_pub_date(block)
    related = [e.id for e in entities[:8]]
    if author_entity:
        related = [author_entity.id] + related

    title = artifact.title or etype.value.replace("_", " ").title()
    if total > 1 and author_entity:
        title = f"{title} — {author_entity.original_value}"

    event = Event(
        type=etype,
        title=title[:120],
        description="",
        start=start,
        publication=pub,
        related_entity_ids=related,
        attributes=attrs,
        supporting_evidence_ids=[artifact.evidence_id] if artifact.evidence_id else [],
        confidence=0.55 if artifact.acquisition_method.value == "search_snippet" else 0.7,
        origin=IntelligenceOrigin.OBSERVED,
        derivation_reason=(
            "Per-entry authored activity from public page"
            if total > 1
            else "Authored activity metadata from public page (not identity ownership)"
        ),
        platform=artifact.metadata.get("platform", ""),
        source_url=artifact.final_url or artifact.source_url,
        excerpt=(block or "")[:280],
        scan_id=artifact.scan_id,
    )
    return author_entity, event


def extract_activities(artifact: PageArtifact) -> tuple[list[Entity], list[Event]]:
    """Convert page content into one or more activity events without ownership claims."""
    if artifact.acquisition_method.value in ("blocked", "error", "unsupported"):
        return [], []

    text = f"{artifact.title}\n{artifact.main_text}"
    entities = extract_entities(artifact)
    blocks = _split_authored_blocks(text)
    if len(blocks) == 1:
        etype = _infer_activity_type(text, source_url=artifact.source_url or artifact.final_url)
        if etype == EventType.OTHER and not artifact.title:
            return entities, []

    events: list[Event] = []
    for index, block in enumerate(blocks):
        author, event = _event_from_block(
            artifact, block, entities=entities, index=index, total=len(blocks)
        )
        if author:
            # Avoid duplicating the same handle already extracted globally unless authorship attr differs.
            existing = next(
                (
                    e
                    for e in entities
                    if e.type == EntityType.HANDLE
                    and e.normalized_value == author.normalized_value
                    and e.attributes.get("authorship") == "page_claimed"
                ),
                None,
            )
            if existing is None:
                entities.append(author)
            else:
                event.related_entity_ids = [
                    existing.id if rid == author.id else rid for rid in event.related_entity_ids
                ]
        events.append(event)

    return entities, events
