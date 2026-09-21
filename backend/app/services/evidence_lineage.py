"""Explicit translations between evidence, artifact, and cluster namespaces."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.intelligence import Entity
from app.services.evidence_clustering import EvidenceCluster
from app.services.page_analyzer import PageArtifact


@dataclass(frozen=True)
class EvidenceLineageIndex:
    artifact_by_evidence: dict[str, str]
    cluster_by_artifact: dict[str, str]
    clusters_by_id: dict[str, EvidenceCluster]

    @classmethod
    def build(
        cls,
        artifacts: list[PageArtifact],
        clusters: list[EvidenceCluster],
    ) -> "EvidenceLineageIndex":
        return cls(
            artifact_by_evidence={a.evidence_id: a.id for a in artifacts if a.evidence_id},
            cluster_by_artifact={
                artifact_id: cluster.id
                for cluster in clusters
                for artifact_id in cluster.member_artifact_ids
            },
            clusters_by_id={cluster.id: cluster for cluster in clusters},
        )

    def cluster_id_for_evidence(self, evidence_id: str) -> str | None:
        artifact_id = self.artifact_by_evidence.get(evidence_id)
        return self.cluster_by_artifact.get(artifact_id or "")

    def independent_count(self, evidence_ids: list[str]) -> int:
        cluster_ids: set[str] = set()
        unclustered: set[str] = set()
        for evidence_id in evidence_ids:
            cluster_id = self.cluster_id_for_evidence(evidence_id)
            if cluster_id:
                cluster_ids.add(cluster_id)
            elif evidence_id:
                unclustered.add(evidence_id)
        count = sum(
            max(1, self.clusters_by_id[cid].independent_source_count)
            for cid in cluster_ids
        ) + len(unclustered)
        return max(1, count)

    def is_mirror_artifact(self, artifact_id: str) -> bool:
        cluster_id = self.cluster_by_artifact.get(artifact_id)
        if not cluster_id:
            return False
        cluster = self.clusters_by_id[cluster_id]
        return cluster.canonical_artifact_id != artifact_id


def independent_sources_by_entity(
    entities: list[Entity],
    lineage: EvidenceLineageIndex,
) -> dict[str, int]:
    """Count independent clusters for each normalized identity candidate."""
    evidence_by_candidate: dict[tuple[str, str], set[str]] = {}
    for entity in entities:
        key = (entity.type.value, entity.normalized_value)
        evidence_by_candidate.setdefault(key, set()).update(entity.supporting_evidence_ids)
    return {
        entity.id: lineage.independent_count(
            sorted(evidence_by_candidate[(entity.type.value, entity.normalized_value)])
        )
        for entity in entities
    }
