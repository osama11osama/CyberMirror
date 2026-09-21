"""Tests for intelligence Entity/Event models (#36)."""

from datetime import date, datetime

from app.models.intelligence import (
    DatePrecision,
    Entity,
    EntityType,
    Event,
    EventType,
    FuzzyDate,
    IntelligenceBundle,
    IntelligenceOrigin,
    normalize_handle,
    parse_fuzzy_date,
    seed_entities_from_profile,
)
from app.models.schemas import IdentityProfile


def test_fuzzy_date_precision_levels():
    assert parse_fuzzy_date("June 2026", year=2026, month=6).precision == DatePrecision.MONTH
    assert parse_fuzzy_date(year=2026).precision == DatePrecision.YEAR
    assert parse_fuzzy_date(year=2026, month=6, day=15).precision == DatePrecision.EXACT_DAY
    assert parse_fuzzy_date("sometime").precision == DatePrecision.UNKNOWN
    assert parse_fuzzy_date(dt=datetime(2026, 6, 15, 12, 0)).precision == DatePrecision.EXACT_DATETIME


def test_publication_and_stay_dates_coexist():
    ev = Event(
        type=EventType.TRAVEL,
        title="Stay",
        start=parse_fuzzy_date("Stayed June 2026", year=2026, month=6),
        publication=parse_fuzzy_date("Reviewed 2026-07-01", year=2026, month=7, day=1),
        supporting_evidence_ids=["ev-1"],
        derivation_reason="Accommodation review stay month",
    )
    assert ev.start.precision == DatePrecision.MONTH
    assert ev.publication.precision == DatePrecision.EXACT_DAY
    assert ev.start.value != ev.publication.value


def test_seed_entities_are_not_observed():
    profile = IdentityProfile(username="JaneDoe", email="Jane@Example.com")
    seeds = seed_entities_from_profile(profile, scan_id="s1")
    assert len(seeds) == 2
    assert all(e.origin == IntelligenceOrigin.SEED for e in seeds)
    assert all(not e.supporting_evidence_ids for e in seeds)
    handle = next(e for e in seeds if e.type == EntityType.HANDLE)
    assert handle.normalized_value == "janedoe"
    assert handle.original_value == "JaneDoe"


def test_entity_event_serialization_and_evidence_links():
    ent = Entity(
        type=EntityType.HANDLE,
        original_value="@traveler",
        normalized_value=normalize_handle("@traveler"),
        supporting_evidence_ids=["ev-a"],
        confidence=0.8,
        origin=IntelligenceOrigin.OBSERVED,
    )
    ev = Event(
        type=EventType.FORUM_POST,
        title="Hello",
        related_entity_ids=[ent.id],
        supporting_evidence_ids=["ev-a"],
        start=FuzzyDate(raw_text="2024", value=date(2024, 1, 1), precision=DatePrecision.YEAR),
    )
    bundle = IntelligenceBundle(entities=[ent], events=[ev])
    raw = bundle.model_dump(mode="json")
    restored = IntelligenceBundle.model_validate(raw)
    assert restored.entities[0].supporting_evidence_ids == ["ev-a"]
    assert restored.events[0].related_entity_ids == [ent.id]


def test_finding_to_structured_example():
    """Synthetic: one finding URL becomes handle entity + forum event."""
    evidence_id = "evidence-obs-1"
    handle = Entity(
        type=EntityType.HANDLE,
        original_value="osint_user",
        normalized_value="osint_user",
        origin=IntelligenceOrigin.OBSERVED,
        supporting_evidence_ids=[evidence_id],
        extraction_method="fixture",
        supporting_context="Author byline on forum page",
    )
    post = Event(
        type=EventType.FORUM_POST,
        title="My trip notes",
        related_entity_ids=[handle.id],
        supporting_evidence_ids=[evidence_id],
        publication=parse_fuzzy_date(year=2025, month=3, day=2),
        excerpt="Short bounded excerpt only.",
        origin=IntelligenceOrigin.OBSERVED,
        derivation_reason="Forum author + title metadata",
    )
    assert post.supporting_evidence_ids == handle.supporting_evidence_ids
    assert handle.id in post.related_entity_ids
