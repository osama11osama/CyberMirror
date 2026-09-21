"""Build Cytoscape-compatible graph from findings + deep intelligence (#64)."""

from __future__ import annotations

from collections import defaultdict

from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingOutcome, GraphData, GraphEdge, GraphNode, IdentityProfile
from app.services.handles import extract_profile_handle


def _extract_handle(url: str, expected_username: str | None = None) -> str | None:
    return extract_profile_handle(url, expected_username=expected_username)


def _is_strong_observation(f: Finding) -> bool:
    if f.platform in ("Summary", "System", "Correlation Engine"):
        return False
    if f.outcome in (FindingOutcome.NEGATIVE, FindingOutcome.SYSTEM, FindingOutcome.INCONCLUSIVE):
        return False
    if f.verification in (
        VerificationState.BLOCKED,
        VerificationState.POSSIBLE,
        VerificationState.NOT_FOUND,
        VerificationState.ERROR,
        VerificationState.INCONCLUSIVE,
    ):
        return False
    return True


def build_graph(profile: IdentityProfile, findings: list[Finding]) -> GraphData:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_ids: set[str] = set()

    def add_node(nid: str, label: str, ntype: str, **data) -> str:
        if nid not in node_ids:
            nodes.append(GraphNode(id=nid, label=label, type=ntype, data=data))
            node_ids.add(nid)
        else:
            for n in nodes:
                if n.id == nid:
                    n.data.update({k: v for k, v in data.items() if v is not None})
                    break
        return nid

    person_id = add_node(
        "person",
        profile.full_name or "Subject",
        "Person",
        role="seed",
        origin="investigator_input",
    )

    if profile.email:
        eid = add_node(
            f"email:{profile.email}", profile.email, "Email",
            role="seed", origin="investigator_input",
        )
        edges.append(GraphEdge(
            id=f"e-{person_id}-{eid}", source=person_id, target=eid,
            label="search input",
        ))

    if profile.username:
        uid = add_node(
            f"user:{profile.username}", profile.username, "Username",
            role="seed", origin="investigator_input",
        )
        edges.append(GraphEdge(
            id=f"e-{person_id}-{uid}", source=person_id, target=uid,
            label="search input",
        ))

    if profile.phone:
        pid = add_node(
            f"phone:{profile.phone}", profile.phone, "Phone",
            role="seed", origin="investigator_input",
        )
        edges.append(GraphEdge(
            id=f"e-{person_id}-{pid}", source=person_id, target=pid,
            label="search input",
        ))

    if profile.website:
        wid = add_node(
            f"web:{profile.website}", profile.website, "Website",
            role="seed", origin="investigator_input",
        )
        edges.append(GraphEdge(
            id=f"e-{person_id}-{wid}", source=person_id, target=wid,
            label="search input",
        ))

    if profile.location:
        lid = add_node(
            f"loc:{profile.location}", profile.location, "Location",
            role="seed", origin="investigator_input",
        )
        edges.append(GraphEdge(
            id=f"e-{person_id}-{lid}", source=person_id, target=lid,
            label="search input",
        ))

    handle_to_findings: dict[str, list[tuple[int, Finding, str]]] = defaultdict(list)
    finding_node_ids: dict[int, str] = {}

    for i, f in enumerate(findings):
        if not f.url and not f.platform:
            continue

        is_derived = f.source == "identity_correlator" or (
            f.evidence and getattr(f.evidence, "kind", None)
            and f.evidence.kind.value == "derived"
        )
        role = "derived" if is_derived else "discovered"
        origin = "derived_correlation" if is_derived else "observed_evidence"

        fid = add_node(
            f"finding:{i}",
            f.platform or f.title[:30],
            "Correlation" if is_derived else (
                "PublicProfile"
                if f.category.value in ("username_discovery", "social_discovery")
                else "Finding"
            ),
            role=role,
            origin=origin,
            risk=f.risk_level.value,
            url=f.url,
            title=f.title,
            snippet=f.snippet,
            description=f.description,
            source=f.source,
            platform=f.platform,
            category=f.category.value,
            outcome=getattr(f.outcome, "value", None),
            verification=getattr(f.verification, "value", None),
            supporting_finding_ids=(f.raw or {}).get("supporting_finding_ids")
            or (f.evidence.corroborating_finding_ids if f.evidence else None),
            reason=(f.evidence.confidence_reason if f.evidence else f.risk_reason) or "",
        )
        finding_node_ids[i] = fid

        if not _is_strong_observation(f) and not is_derived:
            edges.append(GraphEdge(
                id=f"ef-weak-{i}",
                source=person_id,
                target=fid,
                label="weak / unverified",
            ))
            continue

        parent = person_id
        if profile.username and f.category.value == "username_discovery":
            parent = f"user:{profile.username}"
        elif profile.email and f.category.value == "email_exposure":
            parent = f"email:{profile.email}"
        if parent in node_ids:
            edges.append(GraphEdge(
                id=f"ef-{i}",
                source=parent,
                target=fid,
                label=f.source or "observed",
            ))

        handle = _extract_handle(f.url or "", profile.username or None)
        if handle and _is_strong_observation(f):
            handle_to_findings[handle].append((i, f, fid))

    for handle, items in handle_to_findings.items():
        platforms = {f.platform for _, f, _ in items if f.platform}
        if len(platforms) < 2:
            continue
        corr_id = add_node(
            f"corr-handle:{handle}",
            f"Handle @{handle}",
            "Correlation",
            role="derived",
            origin="derived_correlation",
            reason=f"Same handle observed on {len(platforms)} platforms",
            platforms=sorted(platforms),
            verification="likely",
            supporting_finding_ids=[finding_node_ids[i] for i, _, _ in items],
        )
        for i, f, fid in items:
            edges.append(GraphEdge(
                id=f"corr-{handle}-{i}",
                source=corr_id,
                target=fid,
                label="corroborates",
            ))
        if profile.username and handle == profile.username.lower() and f"user:{profile.username}" in node_ids:
            edges.append(GraphEdge(
                id=f"corr-{handle}-seed",
                source=f"user:{profile.username}",
                target=corr_id,
                label="matches seed username",
            ))

    for i, f in enumerate(findings):
        if f.source != "identity_correlator":
            continue
        support_ids = (f.raw or {}).get("supporting_finding_ids") or []
        corr_node = finding_node_ids.get(i)
        if not corr_node:
            continue
        for j, other in enumerate(findings):
            if other.id in support_ids and j in finding_node_ids:
                edges.append(GraphEdge(
                    id=f"support-{i}-{j}",
                    source=corr_node,
                    target=finding_node_ids[j],
                    label="supported by",
                ))

    return GraphData(nodes=nodes, edges=edges)


_ACTIVITY_TYPES = {
    "forum_post",
    "comment",
    "review",
    "social_post",
    "repository_activity",
}
_MENTION_TYPES = {"product", "vehicle", "topic", "technology", "organization"}


def enrich_graph_with_intelligence(graph: GraphData, intel: dict) -> GraphData:
    """Add entity/event/hypothesis/cluster nodes and semantic edges (#64)."""
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    existing = {n.id for n in nodes}
    edge_ids = {e.id for e in edges}

    def add(nid: str, label: str, ntype: str, **data) -> None:
        if nid in existing:
            for n in nodes:
                if n.id == nid:
                    n.data.update({k: v for k, v in data.items() if v is not None})
                    break
            return
        existing.add(nid)
        nodes.append(GraphNode(id=nid, label=label, type=ntype, data=data))

    def link(eid: str, source: str, target: str, label: str) -> None:
        if eid in edge_ids or source not in existing or target not in existing:
            return
        edge_ids.add(eid)
        edges.append(GraphEdge(id=eid, source=source, target=target, label=label))

    entities = intel.get("bundle", {}).get("entities") or []
    events = intel.get("bundle", {}).get("events") or []
    entity_by_id = {e.get("id"): e for e in entities if e.get("id")}

    for ent in entities:
        eid = ent.get("id") or ""
        if not eid:
            continue
        origin = ent.get("origin") or "observed"
        attrs = ent.get("attributes") or {}
        add(
            f"ent:{eid}",
            (ent.get("original_value") or ent.get("normalized_value") or ent.get("type") or "entity")[:60],
            "Entity",
            role="seed" if origin == "seed" else ("derived" if origin == "derived" else "discovered"),
            entity_type=ent.get("type"),
            confidence=ent.get("confidence"),
            origin=origin,
            evidence_ids=ent.get("supporting_evidence_ids") or [],
            authorship=attrs.get("authorship"),
            status=attrs.get("authorship") or origin,
        )

    for ev in events:
        eid = ev.get("id") or ""
        if not eid:
            continue
        start = ev.get("start") or {}
        pub = ev.get("publication") or {}
        add(
            f"event:{eid}",
            (ev.get("title") or ev.get("type") or "event")[:60],
            "Event",
            role="derived" if ev.get("origin") == "derived" else "discovered",
            event_type=ev.get("type"),
            confidence=ev.get("confidence"),
            location=ev.get("location_text") or "",
            evidence_ids=ev.get("supporting_evidence_ids") or [],
            reason=ev.get("derivation_reason") or "",
            precision=start.get("precision") or "unknown",
            stay_raw=start.get("raw_text") or "",
            publication_precision=pub.get("precision") or "",
            publication_raw=pub.get("raw_text") or "",
            source_url=ev.get("source_url") or "",
            origin=ev.get("origin") or "observed",
        )
        for rid in ev.get("related_entity_ids") or []:
            ent = entity_by_id.get(rid) or {}
            etype = ent.get("type")
            if etype in _MENTION_TYPES:
                link(f"ev-mention-{eid}-{rid}", f"event:{eid}", f"ent:{rid}", "mentions")
            attrs = ent.get("attributes") or {}
            if attrs.get("authorship") == "page_claimed" and (ev.get("type") in _ACTIVITY_TYPES):
                link(f"ev-authored-{eid}-{rid}", f"ent:{rid}", f"event:{eid}", "authored")
        loc = ev.get("location_entity_id")
        if loc:
            link(f"ev-loc-{eid}", f"event:{eid}", f"ent:{loc}", "occurred at")

    # Review/activity → travel (shared evidence).
    activity_events = [e for e in events if e.get("type") in _ACTIVITY_TYPES]
    travel_events = [e for e in events if e.get("type") == "travel"]
    for travel in travel_events:
        t_ids = set(travel.get("supporting_evidence_ids") or [])
        tid = travel.get("id")
        if not tid or not t_ids:
            continue
        for activity in activity_events:
            aid = activity.get("id")
            a_ids = set(activity.get("supporting_evidence_ids") or [])
            if aid and t_ids & a_ids:
                link(f"describes-{aid}-{tid}", f"event:{aid}", f"event:{tid}", "describes stay")

    for hyp in intel.get("hypotheses") or []:
        hid = hyp.get("id") or ""
        cand = hyp.get("candidate_entity_id") or ""
        if not hid:
            continue
        add(
            f"hyp:{hid}",
            f"Identity {hyp.get('status', 'unresolved')}: {hyp.get('candidate_value', '')}"[:70],
            "Hypothesis",
            role="derived",
            status=hyp.get("status"),
            confidence=hyp.get("confidence"),
            reasons=hyp.get("reasons") or [],
            evidence_ids=hyp.get("supporting_evidence_ids") or [],
            contradicting_evidence_ids=hyp.get("contradicting_evidence_ids") or [],
            origin="derived",
        )
        link(f"hyp-person-{hid}", "person", f"hyp:{hid}", "investigates")
        if cand:
            link(f"hyp-ent-{hid}", f"hyp:{hid}", f"ent:{cand}", "hypothesized ownership")

    # Evidence clusters + lineage.
    artifacts = {a.get("id"): a for a in (intel.get("artifacts") or []) if a.get("id")}
    evidence_to_artifact = {
        a.get("evidence_id"): a.get("id")
        for a in artifacts.values()
        if a.get("evidence_id")
    }
    for cl in intel.get("clusters") or []:
        cid = cl.get("id") or ""
        if not cid:
            continue
        lineage = cl.get("lineage_type") or "unknown"
        add(
            f"cluster:{cid}",
            f"Evidence cluster ({lineage})",
            "EvidenceCluster",
            role="derived",
            independent=cl.get("independent_source_count"),
            mirrors=cl.get("mirror_count"),
            reason=cl.get("reason") or "",
            lineage_type=lineage,
            canonical_artifact_id=cl.get("canonical_artifact_id") or "",
            member_artifact_ids=cl.get("member_artifact_ids") or [],
            is_mirror_cluster=bool(int(cl.get("mirror_count") or 0)),
            origin="derived",
        )
        for artifact_id in cl.get("member_artifact_ids") or []:
            art = artifacts.get(artifact_id) or {}
            is_canonical = artifact_id == cl.get("canonical_artifact_id")
            add(
                f"artifact:{artifact_id}",
                (art.get("title") or art.get("source_url") or "artifact")[:60],
                "EvidenceArtifact",
                role="discovered",
                origin="observed",
                url=art.get("final_url") or art.get("source_url") or "",
                evidence_id=art.get("evidence_id") or "",
                is_mirror=not is_canonical,
                lineage="canonical" if is_canonical else "mirror",
                acquisition=art.get("acquisition_method") or "",
            )
            link(
                f"cluster-art-{cid}-{artifact_id}",
                f"artifact:{artifact_id}",
                f"cluster:{cid}",
                "member of" if is_canonical else "derived from",
            )

        for hyp in intel.get("hypotheses") or []:
            hid = hyp.get("id") or ""
            for evidence_id in hyp.get("supporting_evidence_ids") or []:
                artifact_id = evidence_to_artifact.get(evidence_id)
                if artifact_id and artifact_id in (cl.get("member_artifact_ids") or []):
                    link(f"hyp-cl-{hid}-{cid}", f"hyp:{hid}", f"cluster:{cid}", "supported by")
                    break

    return GraphData(nodes=nodes, edges=edges)
