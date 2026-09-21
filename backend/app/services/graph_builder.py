"""Build Cytoscape-compatible graph from findings (evidence-backed)."""

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
            # Merge enriching fields onto existing node when re-visited.
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

        # Weak / blocked observations stay on the graph but do not attach as strong links.
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

    # Multi-platform handle corroboration nodes.
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

    # Wire derived correlator nodes to their supporting finding nodes when possible.
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
