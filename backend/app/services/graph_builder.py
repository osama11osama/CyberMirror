"""Build Cytoscape-compatible graph from findings."""

from app.models.schemas import Finding, GraphData, GraphEdge, GraphNode, IdentityProfile


def build_graph(profile: IdentityProfile, findings: list[Finding]) -> GraphData:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_ids: set[str] = set()

    def add_node(nid: str, label: str, ntype: str, **data) -> str:
        if nid not in node_ids:
            nodes.append(GraphNode(id=nid, label=label, type=ntype, data=data))
            node_ids.add(nid)
        return nid

    # Seed / investigator-supplied attributes (search inputs — not public evidence).
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

    for i, f in enumerate(findings):
        if not f.url and not f.platform:
            continue
        fid = add_node(
            f"finding:{i}",
            f.platform or f.title[:30],
            "PublicProfile" if f.category.value in ("username_discovery", "social_discovery") else "Finding",
            role="discovered",
            origin="observed_evidence",
            risk=f.risk_level.value,
            url=f.url,
            title=f.title,
            snippet=f.snippet,
            description=f.description,
            source=f.source,
            platform=f.platform,
            category=f.category.value,
            outcome=getattr(f.outcome, "value", None),
        )
        parent = person_id
        if profile.username and f.category.value == "username_discovery":
            parent = f"user:{profile.username}"
        elif profile.email and f.category.value == "email_exposure":
            parent = f"email:{profile.email}"
        if parent in node_ids:
            edges.append(GraphEdge(
                id=f"ef-{i}", source=parent, target=fid, label=f.source or "observed",
            ))

    return GraphData(nodes=nodes, edges=edges)
