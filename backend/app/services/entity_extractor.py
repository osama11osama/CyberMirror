"""Deterministic entity extraction from PageArtifacts (#38)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models.intelligence import (
    Entity,
    EntityType,
    IntelligenceOrigin,
    normalize_domain,
    normalize_email,
    normalize_handle,
    parse_fuzzy_date,
)
from app.services.page_analyzer import PageArtifact

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3}[\s-]?\d{4}(?!\d)")
_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{2,32})\b")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_MONTH_YEAR_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(20\d{2})\b",
    re.I,
)
_ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_entities(artifact: PageArtifact, *, max_entities: int = 40) -> list[Entity]:
    """Offline deterministic extraction — no paid AI required."""
    text = f"{artifact.title}\n{artifact.main_text}"
    evidence_id = artifact.evidence_id
    out: list[Entity] = []
    seen: set[tuple[str, str]] = set()

    def add(entity: Entity) -> None:
        key = (entity.type.value, entity.normalized_value)
        if not entity.normalized_value or key in seen:
            return
        seen.add(key)
        out.append(entity)

    for m in _EMAIL_RE.finditer(text):
        raw = m.group(0)
        add(
            Entity(
                type=EntityType.EMAIL,
                original_value=raw,
                normalized_value=normalize_email(raw),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="regex_email",
                supporting_context=text[max(0, m.start() - 40) : m.end() + 40][:160],
                confidence=0.85,
                scan_id=artifact.scan_id,
            )
        )

    for m in _HANDLE_RE.finditer(text):
        raw = m.group(0)
        add(
            Entity(
                type=EntityType.HANDLE,
                original_value=raw,
                normalized_value=normalize_handle(raw),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="regex_handle",
                supporting_context=text[max(0, m.start() - 40) : m.end() + 40][:160],
                confidence=0.7,
                scan_id=artifact.scan_id,
            )
        )

    for m in _URL_RE.finditer(text):
        raw = m.group(0).rstrip(").,;")
        host = urlparse(raw).netloc
        if host:
            add(
                Entity(
                    type=EntityType.DOMAIN,
                    original_value=raw,
                    normalized_value=normalize_domain(host),
                    origin=IntelligenceOrigin.OBSERVED,
                    supporting_evidence_ids=[evidence_id] if evidence_id else [],
                    extraction_method="regex_url",
                    attributes={"url": raw},
                    confidence=0.75,
                    scan_id=artifact.scan_id,
                )
            )

    for m in _PHONE_RE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"[^\d+]", "", raw)
        if len(re.sub(r"\D", "", digits)) < 7:
            continue
        add(
            Entity(
                type=EntityType.PHONE,
                original_value=raw,
                normalized_value=digits,
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="regex_phone",
                confidence=0.55,
                scan_id=artifact.scan_id,
            )
        )

    for m in _ISO_DATE_RE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        fuzzy = parse_fuzzy_date(m.group(0), year=y, month=mo, day=d)
        if fuzzy.value is None:
            # ISO-shaped but invalid calendar date (e.g. 2026-99-40) — skip.
            continue
        add(
            Entity(
                type=EntityType.DATETIME_EXPRESSION,
                original_value=m.group(0),
                normalized_value=fuzzy.value.isoformat(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="regex_iso_date",
                attributes={"precision": fuzzy.precision.value},
                confidence=0.8,
                scan_id=artifact.scan_id,
            )
        )

    for m in _MONTH_YEAR_RE.finditer(text):
        mo = _MONTHS[m.group(1).lower()]
        y = int(m.group(2))
        fuzzy = parse_fuzzy_date(m.group(0), year=y, month=mo)
        add(
            Entity(
                type=EntityType.DATETIME_EXPRESSION,
                original_value=m.group(0),
                normalized_value=f"{y:04d}-{mo:02d}",
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="regex_month_year",
                attributes={"precision": fuzzy.precision.value},
                confidence=0.75,
                scan_id=artifact.scan_id,
            )
        )

    # Location: only keep explicit "in City" / "City, Country" style when short.
    loc = re.search(r"\bin ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", text)
    if loc:
        city = loc.group(1)
        add(
            Entity(
                type=EntityType.LOCATION,
                original_value=city,
                normalized_value=city.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="regex_in_city",
                attributes={"specificity": "city_mention"},
                confidence=0.45,
                scan_id=artifact.scan_id,
            )
        )

    return out[:max_entities]


class SemanticExtractor:
    """Optional extension point for AI/semantic extractors (documented interface)."""

    def extract(self, artifact: PageArtifact) -> list[Entity]:
        raise NotImplementedError("Semantic extractors are optional; core path is deterministic.")
