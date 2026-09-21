"""Bounded recursive pivot engine (#45)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.intelligence import Entity, EntityType
from app.models.schemas import IdentityProfile
from app.services.investigation_budget import InvestigationBudget
from app.services.query_planner import PlannedQuery, QueryFamily, build_investigation_plan


class PivotStrength(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class PivotCandidate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str
    strength: PivotStrength
    reason: str
    query: str = ""


@dataclass
class PivotEngineState:
    executed_queries: set[str] = field(default_factory=set)
    visited_urls: set[str] = field(default_factory=set)
    used_pivot_keys: set[str] = field(default_factory=set)
    depth: int = 0
    journal_refs: list[str] = field(default_factory=list)


def score_pivot(entity: Entity) -> PivotCandidate | None:
    if entity.type == EntityType.EMAIL and entity.confidence >= 0.7:
        return PivotCandidate(
            entity_id=entity.id,
            strength=PivotStrength.STRONG,
            reason="Exact public email observation",
        )
    if entity.type == EntityType.HANDLE and len(entity.normalized_value) >= 8:
        return PivotCandidate(
            entity_id=entity.id,
            strength=PivotStrength.STRONG,
            reason="Distinctive exact handle",
        )
    if entity.type in (EntityType.LOCATION, EntityType.ORGANIZATION, EntityType.PRODUCT):
        if entity.confidence >= 0.7:
            return PivotCandidate(
                entity_id=entity.id,
                strength=PivotStrength.MEDIUM,
                reason=f"High-confidence {entity.type.value} co-observed",
            )
        return PivotCandidate(
            entity_id=entity.id,
            strength=PivotStrength.WEAK,
            reason=f"Weak/generic {entity.type.value}",
        )
    if entity.type in (EntityType.TOPIC, EntityType.TECHNOLOGY):
        return PivotCandidate(
            entity_id=entity.id,
            strength=PivotStrength.WEAK,
            reason="Generic technology/topic — no recurse by default",
        )
    return None


def next_pivot_queries(
    profile: IdentityProfile,
    entities: list[Entity],
    budget: InvestigationBudget,
    state: PivotEngineState,
) -> list[PlannedQuery]:
    """Generate follow-up queries for strong/medium pivots within budget."""
    if budget.check_continue() or budget.is_cancelled():
        return []
    if state.depth >= budget.max_pivot_depth:
        return []

    strong_entities: list[Entity] = []
    for ent in entities:
        cand = score_pivot(ent)
        if not cand or cand.strength == PivotStrength.WEAK:
            continue
        key = f"{ent.type.value}:{ent.normalized_value}"
        if key in state.used_pivot_keys:
            continue
        state.used_pivot_keys.add(key)
        strong_entities.append(ent)

    plans = build_investigation_plan(
        profile, discovered_entities=strong_entities, depth=state.depth + 1
    )
    out: list[PlannedQuery] = []
    for p in plans:
        # Recursive pivots must only emit contextual follow-ups, never re-run
        # the full identity/activity/travel/technical seed plan.
        if p.family != QueryFamily.CONTEXTUAL:
            continue
        nq = " ".join(p.query.lower().split())
        if nq in state.executed_queries:
            continue
        if budget.consume_query():
            break
        state.executed_queries.add(nq)
        p.depth = state.depth + 1
        out.append(p)
    if out:
        state.depth += 1
    return out
