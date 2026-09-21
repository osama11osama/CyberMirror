"""Evidence clustering for duplicates/mirrors without inflating corroboration (#40)."""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.services.page_analyzer import PageArtifact


class LineageType(str, Enum):
    ORIGINAL = "original"
    MIRROR = "mirror"
    SYNDICATED = "syndicated"
    CACHED = "cached"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"


class EvidenceCluster(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    canonical_artifact_id: str | None = None
    member_artifact_ids: list[str] = Field(default_factory=list)
    origin_platform: str = ""
    lineage_type: LineageType = LineageType.UNKNOWN
    content_fingerprint: str = ""
    independent_source_count: int = 1
    mirror_count: int = 0
    reason: str = ""
    confidence: float = 0.0


def content_fingerprint(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8", errors="ignore")).hexdigest()


def _host(url: str) -> str:
    from urllib.parse import urlparse

    h = urlparse(url or "").netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def cluster_artifacts(artifacts: list[PageArtifact]) -> list[EvidenceCluster]:
    """Cluster exact duplicates and strong near-duplicates by fingerprint/title."""
    by_fp: dict[str, list[PageArtifact]] = {}
    for a in artifacts:
        if a.acquisition_method.value in ("blocked", "error", "unsupported"):
            continue
        fp = a.content_hash or content_fingerprint(a.main_text or a.title)
        by_fp.setdefault(fp, []).append(a)

    clusters: list[EvidenceCluster] = []
    for fp, members in by_fp.items():
        if len(members) == 1:
            a = members[0]
            clusters.append(
                EvidenceCluster(
                    canonical_artifact_id=a.id,
                    member_artifact_ids=[a.id],
                    origin_platform=_host(a.source_url),
                    lineage_type=LineageType.ORIGINAL,
                    content_fingerprint=fp,
                    independent_source_count=1,
                    mirror_count=0,
                    reason="Single observation",
                    confidence=0.9,
                )
            )
            continue

        # Prefer non-snippet as canonical.
        ordered = sorted(
            members,
            key=lambda x: (
                0 if x.acquisition_method.value != "search_snippet" else 1,
                len(x.main_text or ""),
            ),
        )
        canonical = ordered[-1] if ordered[0].acquisition_method.value == "search_snippet" else ordered[0]
        hosts = {_host(m.source_url) for m in members}
        # Same fingerprint across hosts → mirrors/syndication, not independent.
        independent = 1
        mirror_n = len(members) - 1
        lineage = LineageType.MIRROR if len(hosts) > 1 else LineageType.DUPLICATE
        clusters.append(
            EvidenceCluster(
                canonical_artifact_id=canonical.id,
                member_artifact_ids=[m.id for m in members],
                origin_platform=_host(canonical.source_url),
                lineage_type=lineage,
                content_fingerprint=fp,
                independent_source_count=independent,
                mirror_count=mirror_n,
                reason=(
                    f"Identical/near-identical content across {len(members)} pages "
                    f"({len(hosts)} host(s)); mirrors do not increase independent corroboration"
                ),
                confidence=0.85 if lineage == LineageType.MIRROR else 0.95,
            )
        )
    return clusters


def independent_observation_count(clusters: list[EvidenceCluster]) -> int:
    return sum(max(1, c.independent_source_count) for c in clusters)
