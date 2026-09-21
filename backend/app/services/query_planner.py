"""Contextual query families and structured investigation plans (#43)."""

from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.intelligence import Entity, EntityType
from app.models.schemas import IdentityProfile


class QueryFamily(str, Enum):
    IDENTITY = "identity"
    ACTIVITY = "activity"
    TRAVEL = "travel"
    TECHNICAL = "technical"
    CONTEXTUAL = "contextual"


class QueryState(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PlannedQuery(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    query: str
    family: QueryFamily
    source_seed: str = ""
    pivot_entity_id: str | None = None
    expected_evidence_type: str = ""
    priority: int = 50
    depth: int = 0
    reason: str = ""
    state: QueryState = QueryState.PLANNED


_SITE_PROFILES = (
    ("site:github.com", "GitHub profile/pages", 40),
    ("site:reddit.com", "Reddit activity", 45),
)

_LOW_VALUE_TYPES = {EntityType.TOPIC, EntityType.TECHNOLOGY}


def _norm_query(q: str) -> str:
    return " ".join((q or "").lower().split())


def build_investigation_plan(
    profile: IdentityProfile,
    *,
    discovered_entities: list[Entity] | None = None,
    depth: int = 0,
) -> list[PlannedQuery]:
    """Generate transparent query families from seeds and strong discoveries."""
    handle = (profile.username or "").strip().lstrip("@")
    name = (profile.full_name or "").strip()
    plans: list[PlannedQuery] = []
    seen: set[str] = set()

    def add(
        query: str,
        family: QueryFamily,
        *,
        reason: str,
        priority: int,
        expected: str,
        pivot_id: str | None = None,
        seed: str = "",
    ) -> None:
        key = _norm_query(query)
        if not key or key in seen:
            return
        seen.add(key)
        plans.append(
            PlannedQuery(
                query=query,
                family=family,
                source_seed=seed or handle or name,
                pivot_entity_id=pivot_id,
                expected_evidence_type=expected,
                priority=priority,
                depth=depth,
                reason=reason,
            )
        )

    if handle:
        add(f'"{handle}"', QueryFamily.IDENTITY, reason="Exact quoted handle", priority=10, expected="profile")
        add(handle, QueryFamily.IDENTITY, reason="Exact handle", priority=15, expected="profile")
        if name:
            add(
                f'"{handle}" "{name}"',
                QueryFamily.IDENTITY,
                reason="Handle + real name",
                priority=20,
                expected="identity_page",
            )
        for site, why, pri in _SITE_PROFILES:
            add(f"{site} {handle}", QueryFamily.IDENTITY, reason=why, priority=pri, expected="site_profile")

        for term, fam, exp, pri, why in (
            ("forum", QueryFamily.ACTIVITY, "forum_post", 30, "Handle + forum"),
            ("comment", QueryFamily.ACTIVITY, "comment", 32, "Handle + comment"),
            ("review", QueryFamily.ACTIVITY, "review", 28, "Handle + review"),
            ("post", QueryFamily.ACTIVITY, "social_post", 35, "Handle + post"),
            ("hotel", QueryFamily.TRAVEL, "travel_review", 34, "Handle + hotel"),
            ("stayed", QueryFamily.TRAVEL, "travel_review", 33, "Handle + stayed"),
            ("traveller", QueryFamily.TRAVEL, "travel_review", 36, "Handle + traveller"),
            ("accommodation", QueryFamily.TRAVEL, "travel_review", 37, "Handle + accommodation"),
            ("GitHub", QueryFamily.TECHNICAL, "repo_activity", 38, "Handle + GitHub"),
            ("developer", QueryFamily.TECHNICAL, "tech_profile", 42, "Handle + developer"),
        ):
            add(f'"{handle}" {term}', fam, reason=why, priority=pri, expected=exp)

    # Contextual pivots from high-confidence discovered entities only.
    for ent in discovered_entities or []:
        if ent.type in _LOW_VALUE_TYPES:
            continue
        if ent.confidence < 0.7:
            continue
        if ent.type not in (
            EntityType.LOCATION,
            EntityType.ORGANIZATION,
            EntityType.PRODUCT,
            EntityType.DOMAIN,
            EntityType.EMAIL,
        ):
            continue
        if not handle:
            continue
        val = ent.original_value or ent.normalized_value
        if len(val) < 3:
            continue
        add(
            f'"{handle}" "{val}"',
            QueryFamily.CONTEXTUAL,
            reason=f"Contextual pivot from {ent.type.value}",
            priority=25,
            expected="contextual_hit",
            pivot_id=ent.id,
        )

    plans.sort(key=lambda p: (p.priority, p.query))
    return plans
