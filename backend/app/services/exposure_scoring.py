"""Evidence-aware exposure scoring (v2.4+).

Replaces arithmetic-mean severity with a peak-dominated, deduplicated score.
Inconclusive / blocked / negative / system findings do not inflate exposure.
See docs/exposure-scoring.md for examples.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingOutcome, RiskLevel

RISK_WEIGHTS = {
    RiskLevel.CRITICAL: 100,
    RiskLevel.HIGH: 75,
    RiskLevel.MEDIUM: 50,
    RiskLevel.LOW: 25,
    RiskLevel.INFO: 10,
    RiskLevel.UNKNOWN: 0,
}

DISCLAIMER = (
    "Heuristic exposure indicator based on observed findings — "
    "not an objective probability of harm."
)

_VERIFICATION_FACTOR = {
    VerificationState.VERIFIED: 1.0,
    VerificationState.LIKELY: 0.88,
    VerificationState.POSSIBLE: 0.45,
    VerificationState.NOT_FOUND: 0.0,
    VerificationState.INCONCLUSIVE: 0.2,
    VerificationState.BLOCKED: 0.15,
    VerificationState.ERROR: 0.0,
    VerificationState.UNKNOWN: 0.75,
}


@dataclass
class ExposureScoreResult:
    score: float
    method: str = "evidence_aware_v1"
    reasons: list[str] = field(default_factory=list)
    contributing: list[dict] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "method": self.method,
            "reasons": self.reasons,
            "contributing": self.contributing[:12],
            "disclaimer": self.disclaimer,
        }


def _outcome_of(finding: Finding) -> FindingOutcome:
    if finding.outcome and finding.outcome != FindingOutcome.UNKNOWN:
        return finding.outcome
    raw = (finding.raw or {}).get("outcome")
    if isinstance(raw, str):
        try:
            return FindingOutcome(raw)
        except ValueError:
            pass
    return FindingOutcome.UNKNOWN


def _dedupe_key(finding: Finding) -> str:
    url = (finding.url or "").strip().lower()
    if url:
        return f"url:{url}"
    return f"plat:{(finding.platform or '').lower()}|{(finding.title or '')[:60].lower()}"


def _is_derived_finding(finding: Finding) -> bool:
    if finding.source == "identity_correlator":
        return True
    if finding.platform == "Correlation Engine":
        return True
    evidence = finding.evidence
    if evidence is not None and getattr(evidence, "kind", None) is not None:
        kind = evidence.kind
        value = kind.value if hasattr(kind, "value") else str(kind)
        if value == "derived":
            return True
    raw = finding.raw or {}
    # Any conclusion that cites other findings is not an independent observation.
    if raw.get("supporting_finding_ids"):
        return True
    return False


def _is_exposure_candidate(finding: Finding) -> bool:
    if _is_derived_finding(finding):
        return False
    outcome = _outcome_of(finding)
    if outcome in (
        FindingOutcome.NEGATIVE,
        FindingOutcome.SYSTEM,
        FindingOutcome.INCONCLUSIVE,
    ):
        return False
    if finding.verification in (
        VerificationState.NOT_FOUND,
        VerificationState.BLOCKED,
        VerificationState.ERROR,
        VerificationState.INCONCLUSIVE,
        VerificationState.POSSIBLE,
    ):
        return False
    if finding.platform in ("Summary", "System"):
        return False
    if finding.risk_level in (RiskLevel.INFO, RiskLevel.UNKNOWN):
        return False
    return True


def _effective_weight(finding: Finding) -> float:
    base = float(RISK_WEIGHTS.get(finding.risk_level, 0))
    v = finding.verification or VerificationState.UNKNOWN
    factor = _VERIFICATION_FACTOR.get(v, 0.75)
    conf = finding.confidence if finding.confidence and finding.confidence > 0 else 0.7
    conf_factor = 0.55 + 0.45 * min(1.0, conf)
    return base * factor * conf_factor


def compute_exposure_score(findings: list[Finding]) -> ExposureScoreResult:
    """Peak-dominated score with dedupe and corroboration bonus."""
    if not findings:
        return ExposureScoreResult(score=0.0, reasons=["No findings to score"])

    best: dict[str, tuple[float, Finding]] = {}
    skipped_inconclusive = 0
    for f in findings:
        if not _is_exposure_candidate(f):
            if _outcome_of(f) == FindingOutcome.INCONCLUSIVE or f.verification in (
                VerificationState.BLOCKED,
                VerificationState.POSSIBLE,
                VerificationState.INCONCLUSIVE,
            ):
                skipped_inconclusive += 1
            continue
        key = _dedupe_key(f)
        weight = _effective_weight(f)
        prev = best.get(key)
        if prev is None or weight > prev[0]:
            best[key] = (weight, f)

    if not best:
        reasons = ["No confirmed exposure findings after filtering"]
        if skipped_inconclusive:
            reasons.append(
                f"Ignored {skipped_inconclusive} inconclusive/blocked/possible check(s)"
            )
        return ExposureScoreResult(score=0.0, reasons=reasons)

    ranked = sorted(best.values(), key=lambda t: t[0], reverse=True)
    weights = [w for w, _ in ranked]
    top = ranked[0]

    score = weights[0] * 0.72
    if len(weights) > 1:
        score += weights[1] * 0.18
    if len(weights) > 2:
        score += weights[2] * 0.08
    if len(weights) > 3:
        score += min(10.0, sum(weights[3:8]) * 0.02)

    platforms = {
        (f.platform or f.source or "").lower()
        for _, f in ranked[:8]
        if (f.platform or f.source)
    }
    if len(platforms) >= 3:
        score += 6.0
    elif len(platforms) >= 2:
        score += 3.0

    score = round(min(100.0, score), 1)

    reasons = [
        f"Top exposure: {top[1].title[:80] or top[1].platform} "
        f"({top[1].risk_level.value}, weight {top[0]:.0f})",
        f"Counted {len(ranked)} unique evidence item(s) after deduplication",
    ]
    if len(weights) > 1:
        reasons.append(
            f"Secondary signals contributed "
            f"{round(min(100.0, max(0.0, score - weights[0] * 0.72)), 1)} points"
        )
    if len(platforms) >= 2:
        reasons.append(f"Independent platforms observed: {len(platforms)}")
    if skipped_inconclusive:
        reasons.append(
            f"Excluded {skipped_inconclusive} inconclusive/blocked/possible finding(s)"
        )
    reasons.append(DISCLAIMER)

    contributing = [
        {
            "title": f.title,
            "platform": f.platform,
            "risk": f.risk_level.value,
            "verification": getattr(f.verification, "value", "unknown"),
            "weight": round(w, 1),
        }
        for w, f in ranked[:8]
    ]
    return ExposureScoreResult(
        score=score, reasons=reasons, contributing=contributing
    )


def compute_risk_score(findings: list[Finding]) -> float:
    """Compatibility wrapper used by scan engine / dashboard."""
    return compute_exposure_score(findings).score
