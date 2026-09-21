"""Deterministic entity extraction from PageArtifacts (#38 / #61)."""

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
from app.services.structured_page import parse_structured_signals, social_profile_from_url

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

_ORG_LABEL_RE = re.compile(
    r"\b(?:company|organization|organisation|employer|corp(?:oration)?)\s*[:=]\s*"
    r"([A-Z][\w .&'-]{1,60})",
    re.I,
)
_PRODUCT_LABEL_RE = re.compile(
    r"\b(?:product|model)\s*[:=]\s*([A-Za-z0-9][\w .+\-]{1,60})",
    re.I,
)
_VEHICLE_LABEL_RE = re.compile(
    r"\b(?:vehicle|car|make(?:/model)?)\s*[:=]\s*([A-Za-z0-9][\w .+\-]{1,60})",
    re.I,
)
_VIN_RE = re.compile(r"\bVIN\s*[:=]?\s*([A-HJ-NPR-Z0-9]{11,17})\b", re.I)
_TECH_CONTEXT_RE = re.compile(
    r"\b(?:built with|powered by|uses|using|written in|stack(?: is)?)\s+"
    r"(Python|JavaScript|TypeScript|Go|Rust|Java|Docker|Kubernetes|React|Angular)\b",
    re.I,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# Common words that must never become high-confidence orgs/products from bare caps.
_STOP_CAPS = {
    "the", "this", "that", "with", "from", "review", "posted", "author", "hotel",
    "forum", "comment", "thread", "january", "february", "march", "april", "may",
    "june", "july", "august", "september", "october", "november", "december",
}


def extract_entities(artifact: PageArtifact, *, max_entities: int = 40) -> list[Entity]:
    """Offline deterministic extraction — structured signals before free text."""
    text = f"{artifact.title}\n{artifact.main_text}"
    evidence_id = artifact.evidence_id
    out: list[Entity] = []
    seen: set[tuple[str, str]] = set()
    structured_location = False

    def add(entity: Entity) -> None:
        key = (entity.type.value, entity.normalized_value)
        if not entity.normalized_value or key in seen:
            return
        seen.add(key)
        out.append(entity)

    def _ctx(start: int, end: int) -> str:
        return text[max(0, start - 40) : end + 40][:160]

    signals = parse_structured_signals(artifact.main_text or "")
    # Prefer structured signals captured from raw HTML before tag stripping.
    cached = artifact.metadata.get("structured") if isinstance(artifact.metadata, dict) else None
    if isinstance(cached, dict):
        from app.services.structured_page import StructuredSignals

        signals = StructuredSignals(
            organizations=list(cached.get("organizations") or signals.organizations),
            products=list(cached.get("products") or signals.products),
            locations=list(cached.get("locations") or signals.locations),
            authors=list(cached.get("authors") or signals.authors),
            social_profiles=list(cached.get("social_profiles") or signals.social_profiles),
            vehicles=list(cached.get("vehicles") or signals.vehicles),
        )

    for org in signals.organizations:
        name = str(org.get("name") or "").strip()
        if len(name) < 2 or name.lower() in _STOP_CAPS:
            continue
        add(
            Entity(
                type=EntityType.ORGANIZATION,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method=f"structured_{org.get('source', 'org')}",
                supporting_context=name[:160],
                confidence=0.82,
                scan_id=artifact.scan_id,
                attributes={"source": org.get("source", "structured")},
            )
        )

    for product in signals.products:
        name = str(product.get("name") or "").strip()
        if len(name) < 2:
            continue
        add(
            Entity(
                type=EntityType.PRODUCT,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method=f"structured_{product.get('source', 'product')}",
                confidence=0.8,
                scan_id=artifact.scan_id,
            )
        )

    for vehicle in signals.vehicles:
        name = str(vehicle.get("name") or "").strip()
        if len(name) < 2:
            continue
        add(
            Entity(
                type=EntityType.VEHICLE,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="structured_vehicle",
                confidence=0.8,
                scan_id=artifact.scan_id,
            )
        )

    for loc in signals.locations:
        name = str(loc.get("name") or "").strip()
        if len(name) < 2:
            continue
        structured_location = True
        add(
            Entity(
                type=EntityType.LOCATION,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method=f"structured_{loc.get('source', 'location')}",
                attributes={"specificity": "structured_metadata"},
                confidence=0.85,
                scan_id=artifact.scan_id,
            )
        )

    for profile in signals.social_profiles:
        handle = str(profile.get("handle") or "").strip()
        platform = str(profile.get("platform") or "").strip()
        url = str(profile.get("url") or "").strip()
        if not handle and url:
            resolved = social_profile_from_url(url)
            if resolved:
                handle = resolved["handle"]
                platform = platform or resolved["platform"]
                url = resolved["url"]
        if not handle:
            continue
        add(
            Entity(
                type=EntityType.SOCIAL_ACCOUNT,
                original_value=f"{platform}:{handle}" if platform else handle,
                normalized_value=normalize_handle(handle),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="structured_social_profile",
                attributes={"platform": platform, "url": url},
                confidence=0.8,
                scan_id=artifact.scan_id,
            )
        )

    for author in signals.authors:
        name = str(author.get("name") or "").strip()
        url = str(author.get("url") or "").strip()
        if url:
            profile = social_profile_from_url(url)
            if profile:
                add(
                    Entity(
                        type=EntityType.SOCIAL_ACCOUNT,
                        original_value=f"{profile['platform']}:{profile['handle']}",
                        normalized_value=normalize_handle(profile["handle"]),
                        origin=IntelligenceOrigin.OBSERVED,
                        supporting_evidence_ids=[evidence_id] if evidence_id else [],
                        extraction_method="structured_author_url",
                        attributes={"platform": profile["platform"], "url": url, "authorship": "page_claimed"},
                        confidence=0.78,
                        scan_id=artifact.scan_id,
                    )
                )
        if name and not name.startswith("http") and re.fullmatch(r"[A-Za-z0-9_.\-]{2,40}", name):
            add(
                Entity(
                    type=EntityType.HANDLE,
                    original_value=name,
                    normalized_value=normalize_handle(name),
                    origin=IntelligenceOrigin.OBSERVED,
                    supporting_evidence_ids=[evidence_id] if evidence_id else [],
                    extraction_method="structured_author",
                    attributes={"authorship": "page_claimed", "not_identity_proof": True},
                    confidence=0.75,
                    scan_id=artifact.scan_id,
                )
            )

    # Labeled free-text fields (still explicit — not bare capitalization).
    for m in _ORG_LABEL_RE.finditer(text):
        name = m.group(1).strip().rstrip(".,;")
        if len(name) < 2 or name.lower() in _STOP_CAPS:
            continue
        add(
            Entity(
                type=EntityType.ORGANIZATION,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="labeled_organization",
                supporting_context=_ctx(m.start(), m.end()),
                confidence=0.78,
                scan_id=artifact.scan_id,
            )
        )

    for m in _PRODUCT_LABEL_RE.finditer(text):
        name = m.group(1).strip().rstrip(".,;")
        add(
            Entity(
                type=EntityType.PRODUCT,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="labeled_product",
                supporting_context=_ctx(m.start(), m.end()),
                confidence=0.75,
                scan_id=artifact.scan_id,
            )
        )

    for m in _VEHICLE_LABEL_RE.finditer(text):
        name = m.group(1).strip().rstrip(".,;")
        add(
            Entity(
                type=EntityType.VEHICLE,
                original_value=name,
                normalized_value=name.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="labeled_vehicle",
                supporting_context=_ctx(m.start(), m.end()),
                confidence=0.75,
                scan_id=artifact.scan_id,
                attributes={"version": "unknown"},
            )
        )

    for m in _VIN_RE.finditer(text):
        vin = m.group(1).upper()
        add(
            Entity(
                type=EntityType.VEHICLE,
                original_value=vin,
                normalized_value=vin.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="labeled_vin",
                confidence=0.7,
                scan_id=artifact.scan_id,
                attributes={"identifier": "vin", "version": "unknown"},
            )
        )

    for m in _TECH_CONTEXT_RE.finditer(text):
        tech = m.group(1)
        add(
            Entity(
                type=EntityType.TECHNOLOGY,
                original_value=tech,
                normalized_value=tech.lower(),
                origin=IntelligenceOrigin.OBSERVED,
                supporting_evidence_ids=[evidence_id] if evidence_id else [],
                extraction_method="contextual_technology",
                supporting_context=_ctx(m.start(), m.end()),
                confidence=0.4,
                scan_id=artifact.scan_id,
                attributes={"pivot_eligible": False},
            )
        )

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
                supporting_context=_ctx(m.start(), m.end()),
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
                supporting_context=_ctx(m.start(), m.end()),
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
        profile = social_profile_from_url(raw)
        if profile:
            add(
                Entity(
                    type=EntityType.SOCIAL_ACCOUNT,
                    original_value=f"{profile['platform']}:{profile['handle']}",
                    normalized_value=normalize_handle(profile["handle"]),
                    origin=IntelligenceOrigin.OBSERVED,
                    supporting_evidence_ids=[evidence_id] if evidence_id else [],
                    extraction_method="url_social_profile",
                    attributes={"platform": profile["platform"], "url": raw},
                    confidence=0.78,
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

    # Weak city heuristic only when structured location was absent.
    if not structured_location:
        loc = re.search(r"\bin ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", text)
        if loc:
            city = loc.group(1)
            if city.lower() not in _STOP_CAPS:
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
