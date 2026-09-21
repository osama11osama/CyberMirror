"""First-class intelligence entity and event models (CyberMirror v2.5 / #36).

These sit above Finding/EvidenceObservation: findings answer \"what was observed\",
while Entity/Event answer \"what structured facts were extracted\" with provenance.

Backward compatibility
----------------------
- Findings and evidence from v2.3/v2.4 remain unchanged.
- Entities/events are additive; older scans simply have empty intelligence payloads.
- Seed/input attributes must use ``origin=seed`` and never masquerade as discovered.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.services.timeutil import utc_now


class DatePrecision(str, Enum):
    """How precisely a date is known — never invent finer precision."""

    EXACT_DATETIME = "exact_datetime"
    EXACT_DAY = "exact_day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    PERSON = "person"
    HANDLE = "handle"
    EMAIL = "email"
    PHONE = "phone"
    SOCIAL_ACCOUNT = "social_account"
    LOCATION = "location"
    ORGANIZATION = "organization"
    DOMAIN = "domain"
    PRODUCT = "product"
    VEHICLE = "vehicle"
    TECHNOLOGY = "technology"
    TOPIC = "topic"
    DATETIME_EXPRESSION = "datetime_expression"
    OTHER = "other"


class EventType(str, Enum):
    FORUM_POST = "forum_post"
    COMMENT = "comment"
    REVIEW = "review"
    SOCIAL_POST = "social_post"
    TRAVEL = "travel"
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    ACCOUNT_CREATION = "account_creation"
    REPOSITORY_ACTIVITY = "repository_activity"
    OTHER = "other"


class IntelligenceOrigin(str, Enum):
    """How the fact entered the investigation."""

    SEED = "seed"  # investigator-supplied — not public evidence
    OBSERVED = "observed"  # extracted from acquired public content
    DERIVED = "derived"  # inferred from observations (must cite evidence)


class FuzzyDate(BaseModel):
    """A date with explicit precision; unknown stays unknown."""

    raw_text: str = ""
    value: date | None = None
    precision: DatePrecision = DatePrecision.UNKNOWN
    datetime_value: datetime | None = None

    def sort_key(self) -> tuple[int, str]:
        """Stable chronological key; UNKNOWN sorts last within a group."""
        if self.precision == DatePrecision.UNKNOWN or self.value is None:
            return (9, "9999-99-99")
        return (0, self.value.isoformat())


class Entity(BaseModel):
    """Normalized person/place/thing extracted or seeded in an investigation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EntityType = EntityType.OTHER
    original_value: str = ""
    normalized_value: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    origin: IntelligenceOrigin = IntelligenceOrigin.OBSERVED
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    extraction_method: str = ""
    supporting_context: str = ""
    scan_id: str = ""


class Event(BaseModel):
    """Structured activity or life event with provenance and date precision."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EventType = EventType.OTHER
    title: str = ""
    description: str = ""
    start: FuzzyDate = Field(default_factory=FuzzyDate)
    end: FuzzyDate | None = None
    # Distinct from start/end: when the source content was published.
    publication: FuzzyDate = Field(default_factory=FuzzyDate)
    collected_at: datetime = Field(default_factory=utc_now)
    related_entity_ids: list[str] = Field(default_factory=list)
    location_entity_id: str | None = None
    location_text: str = ""
    location_reason: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    origin: IntelligenceOrigin = IntelligenceOrigin.OBSERVED
    derivation_reason: str = ""
    platform: str = ""
    source_url: str = ""
    excerpt: str = ""
    scan_id: str = ""


class IntelligenceBundle(BaseModel):
    """Serializable intelligence payload for a scan (API / export / persistence)."""

    entities: list[Entity] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    version: str = "intelligence_v1"


def normalize_handle(value: str) -> str:
    return (value or "").strip().lstrip("@").lower()


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_domain(value: str) -> str:
    v = (value or "").strip().lower()
    if v.startswith("www."):
        v = v[4:]
    return v


def parse_fuzzy_date(
    raw_text: str = "",
    *,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    dt: datetime | None = None,
) -> FuzzyDate:
    """Build a FuzzyDate without inventing missing precision."""
    raw = (raw_text or "").strip()
    if dt is not None:
        return FuzzyDate(
            raw_text=raw or dt.isoformat(),
            value=dt.date(),
            precision=DatePrecision.EXACT_DATETIME,
            datetime_value=dt,
        )
    try:
        if year is not None and month is not None and day is not None:
            return FuzzyDate(
                raw_text=raw or f"{year:04d}-{month:02d}-{day:02d}",
                value=date(year, month, day),
                precision=DatePrecision.EXACT_DAY,
            )
        if year is not None and month is not None:
            return FuzzyDate(
                raw_text=raw or f"{year:04d}-{month:02d}",
                value=date(year, month, 1),
                precision=DatePrecision.MONTH,
            )
        if year is not None:
            return FuzzyDate(
                raw_text=raw or f"{year:04d}",
                value=date(year, 1, 1),
                precision=DatePrecision.YEAR,
            )
    except ValueError:
        return FuzzyDate(raw_text=raw, precision=DatePrecision.UNKNOWN)
    return FuzzyDate(raw_text=raw, precision=DatePrecision.UNKNOWN)


def seed_entities_from_profile(profile: Any, scan_id: str = "") -> list[Entity]:
    """Convert investigator seed fields into seed-origin entities (not discoveries)."""
    out: list[Entity] = []
    mapping = [
        ("username", EntityType.HANDLE, normalize_handle),
        ("email", EntityType.EMAIL, normalize_email),
        ("phone", EntityType.PHONE, lambda v: "".join(c for c in v if c.isdigit() or c == "+")),
        ("full_name", EntityType.PERSON, lambda v: " ".join(v.split()).strip()),
        ("location", EntityType.LOCATION, lambda v: v.strip()),
        ("website", EntityType.DOMAIN, normalize_domain),
        ("company", EntityType.ORGANIZATION, lambda v: v.strip()),
    ]
    for attr, etype, norm in mapping:
        original = (getattr(profile, attr, None) or "").strip()
        if not original:
            continue
        out.append(
            Entity(
                type=etype,
                original_value=original,
                normalized_value=norm(original) or original.lower(),
                origin=IntelligenceOrigin.SEED,
                confidence=1.0,
                extraction_method="seed_profile",
                supporting_context="Investigator-supplied seed — not public evidence",
                scan_id=scan_id,
                attributes={"seed_field": attr},
            )
        )
    return out
