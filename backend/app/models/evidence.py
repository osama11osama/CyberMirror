"""Evidence, provenance, and verification models (CyberMirror 2.3+).

Backward compatibility
----------------------
- New fields live on ``Finding`` and are also mirrored into ``raw_json`` on save
  (`verification`, `evidence`) so older readers that only inspect ``raw`` still work.
- Findings persisted before 2.3 have no verification/evidence; loaders default to
  UNKNOWN / empty evidence and risk_engine falls back to legacy heuristics.
- ``FindingOutcome`` remains the exposure-semantic label used by risk scoring;
  ``VerificationState`` describes scanner certainty and must not be equated with risk.

See also: docs/evidence-model.md
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.services.timeutil import utc_now


class VerificationState(str, Enum):
    """Scanner certainty — independent from RiskLevel / FindingOutcome."""

    VERIFIED = "verified"
    LIKELY = "likely"
    POSSIBLE = "possible"
    NOT_FOUND = "not_found"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"
    ERROR = "error"
    UNKNOWN = "unknown"


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"  # direct remote observation
    DERIVED = "derived"  # correlator / inferred
    SEED = "seed"  # investigator-supplied (not public evidence)


class EvidenceObservation(BaseModel):
    """Structured provenance for a finding claim."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: EvidenceKind = EvidenceKind.OBSERVATION
    method: str = ""  # http | playwright | api | correlator | ...
    queried_identifier: str = ""
    identifier_type: str = ""  # username | email | phone | name | ...
    source_url: str = ""
    platform: str = ""
    collected_at: Any = Field(default_factory=utc_now)
    http_status: int | None = None
    positive_markers: list[str] = Field(default_factory=list)
    negative_markers: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    confidence_reason: str = ""
    corroborating_finding_ids: list[str] = Field(default_factory=list)
    verification: VerificationState = VerificationState.UNKNOWN
    extras: dict[str, Any] = Field(default_factory=dict)


# Phrases that indicate bot walls / login interstitials rather than a profile.
BLOCK_MARKERS = (
    "captcha",
    "cf-challenge",
    "just a moment",
    "enable javascript",
    "checking your browser",
    "access denied",
    "unusual traffic",
    "verify you are human",
    "login to continue",
    "log in to continue",
    "sign in to continue",
    "create an account",
    "are you a robot",
)


def detect_block_reason(text: str, title: str = "") -> str | None:
    blob = f"{title} {text}".lower()
    for marker in BLOCK_MARKERS:
        if marker in blob:
            return marker
    return None


def verification_to_outcome(state: VerificationState):
    """Map verification → FindingOutcome for risk gating (not severity itself)."""
    from app.models.schemas import FindingOutcome

    if state == VerificationState.VERIFIED:
        return FindingOutcome.CONFIRMED
    if state == VerificationState.LIKELY:
        return FindingOutcome.CONFIRMED
    if state == VerificationState.POSSIBLE:
        return FindingOutcome.INCONCLUSIVE
    if state == VerificationState.NOT_FOUND:
        return FindingOutcome.NEGATIVE
    if state in (VerificationState.INCONCLUSIVE, VerificationState.BLOCKED):
        return FindingOutcome.INCONCLUSIVE
    if state == VerificationState.ERROR:
        return FindingOutcome.SYSTEM
    return FindingOutcome.UNKNOWN


def confidence_for_verification(state: VerificationState) -> float:
    return {
        VerificationState.VERIFIED: 0.92,
        VerificationState.LIKELY: 0.78,
        VerificationState.POSSIBLE: 0.55,
        VerificationState.NOT_FOUND: 0.7,
        VerificationState.INCONCLUSIVE: 0.35,
        VerificationState.BLOCKED: 0.3,
        VerificationState.ERROR: 0.0,
        VerificationState.UNKNOWN: 0.0,
    }.get(state, 0.0)
