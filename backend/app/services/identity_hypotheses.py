"""Evidence-backed identity hypotheses (#41)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.intelligence import (
    Entity,
    EntityType,
    IntelligenceOrigin,
    normalize_email,
    normalize_handle,
)
from app.models.schemas import IdentityProfile
from app.services.timeutil import utc_now


class HypothesisStatus(str, Enum):
    VERIFIED = "verified"
    LIKELY = "likely"
    POSSIBLE = "possible"
    UNLIKELY = "unlikely"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class IdentityHypothesis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    target_person_label: str = ""
    candidate_entity_id: str = ""
    candidate_value: str = ""
    status: HypothesisStatus = HypothesisStatus.UNRESOLVED
    confidence: float = 0.0
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utc_now)
    scan_id: str = ""


def _is_rare_handle(handle: str) -> bool:
    h = normalize_handle(handle)
    if len(h) >= 8 and any(c.isdigit() for c in h):
        return True
    if len(h) >= 10:
        return True
    return False


def evaluate_handle_hypothesis(
    profile: IdentityProfile,
    entity: Entity,
    *,
    cross_linked: bool = False,
    independent_sources: int = 1,
    contradicting: bool = False,
    contradicting_evidence_ids: list[str] | None = None,
) -> IdentityHypothesis:
    """Explainable ownership hypothesis — never auto-verify from username alone."""
    seed = normalize_handle(profile.username or "")
    cand = entity.normalized_value or normalize_handle(entity.original_value)
    hyp = IdentityHypothesis(
        target_person_label=profile.full_name or profile.username or "target",
        candidate_entity_id=entity.id,
        candidate_value=entity.original_value or cand,
        supporting_evidence_ids=list(entity.supporting_evidence_ids),
        contradicting_evidence_ids=list(contradicting_evidence_ids or []),
        scan_id=entity.scan_id,
    )
    if entity.origin == IntelligenceOrigin.SEED:
        hyp.status = HypothesisStatus.UNRESOLVED
        hyp.reasons.append("Seed identifier is input, not a discovery hypothesis")
        return hyp

    if contradicting:
        hyp.status = HypothesisStatus.CONTRADICTED
        hyp.confidence = 0.15
        hyp.reasons.append("Contradicting evidence observed for this candidate")
        return hyp

    if not seed or seed != cand:
        hyp.status = HypothesisStatus.POSSIBLE if cand else HypothesisStatus.UNRESOLVED
        hyp.confidence = 0.25
        hyp.reasons.append("Candidate handle does not match seed username")
        return hyp

    reasons = ["Exact handle match with seed username"]
    score = 0.45
    if _is_rare_handle(cand):
        score += 0.15
        reasons.append("Handle appears relatively distinctive (length/digits)")
    else:
        reasons.append("Exact handle match alone does not verify ownership")

    if independent_sources >= 2:
        score += 0.15
        reasons.append(f"{independent_sources} independent sources (mirrors excluded)")
    if cross_linked:
        score += 0.2
        reasons.append("Direct public cross-link between profiles")

    score = min(0.92, score)
    hyp.confidence = round(score, 2)
    hyp.reasons = reasons
    if score >= 0.85 and cross_linked and independent_sources >= 2:
        hyp.status = HypothesisStatus.VERIFIED
    elif score >= 0.7:
        hyp.status = HypothesisStatus.LIKELY
    elif score >= 0.45:
        hyp.status = HypothesisStatus.POSSIBLE
    else:
        hyp.status = HypothesisStatus.UNLIKELY
    return hyp


def evaluate_email_hypothesis(
    profile: IdentityProfile,
    entity: Entity,
    *,
    cross_linked: bool = False,
    independent_sources: int = 1,
    contradicting: bool = False,
    contradicting_evidence_ids: list[str] | None = None,
) -> IdentityHypothesis:
    """Compare observed emails against the email seed — not the username."""
    seed = normalize_email(profile.email or "")
    cand = normalize_email(entity.normalized_value or entity.original_value)
    hyp = IdentityHypothesis(
        target_person_label=profile.full_name or profile.username or profile.email or "target",
        candidate_entity_id=entity.id,
        candidate_value=entity.original_value or cand,
        supporting_evidence_ids=list(entity.supporting_evidence_ids),
        contradicting_evidence_ids=list(contradicting_evidence_ids or []),
        scan_id=entity.scan_id,
    )
    if entity.origin == IntelligenceOrigin.SEED:
        hyp.status = HypothesisStatus.UNRESOLVED
        hyp.reasons.append("Seed identifier is input, not a discovery hypothesis")
        return hyp
    if contradicting:
        hyp.status = HypothesisStatus.CONTRADICTED
        hyp.confidence = 0.15
        hyp.reasons.append("Contradicting evidence observed for this email candidate")
        return hyp
    if not seed:
        hyp.status = HypothesisStatus.UNRESOLVED
        hyp.confidence = 0.2
        hyp.reasons.append("No email seed provided — observed email is not an ownership match")
        return hyp
    if seed != cand:
        hyp.status = HypothesisStatus.UNLIKELY
        hyp.confidence = 0.2
        hyp.reasons.append("Observed email does not match seed email")
        return hyp

    reasons = ["Exact email match with seed email"]
    score = 0.7
    if independent_sources >= 2:
        score += 0.1
        reasons.append(f"{independent_sources} independent sources (mirrors excluded)")
    if cross_linked:
        score += 0.1
        reasons.append("Direct public cross-link supporting this email")
    hyp.confidence = round(min(0.92, score), 2)
    hyp.reasons = reasons
    if hyp.confidence >= 0.85 and cross_linked:
        hyp.status = HypothesisStatus.VERIFIED
    elif hyp.confidence >= 0.7:
        hyp.status = HypothesisStatus.LIKELY
    else:
        hyp.status = HypothesisStatus.POSSIBLE
    return hyp


def build_identity_hypotheses(
    profile: IdentityProfile,
    entities: list[Entity],
    *,
    independent_by_entity: dict[str, int] | None = None,
    cross_linked_ids: set[str] | None = None,
) -> list[IdentityHypothesis]:
    indep = independent_by_entity or {}
    linked = cross_linked_ids or set()
    out: list[IdentityHypothesis] = []
    for ent in entities:
        if ent.origin == IntelligenceOrigin.SEED:
            continue
        if ent.type == EntityType.EMAIL:
            out.append(
                evaluate_email_hypothesis(
                    profile,
                    ent,
                    cross_linked=ent.id in linked,
                    independent_sources=indep.get(ent.id, 1),
                )
            )
            continue
        if ent.type not in (EntityType.HANDLE, EntityType.SOCIAL_ACCOUNT):
            continue
        out.append(
            evaluate_handle_hypothesis(
                profile,
                ent,
                cross_linked=ent.id in linked,
                independent_sources=indep.get(ent.id, 1),
            )
        )
    return out
