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

    person_id = add_node("person", profile.full_name or "Subject", "Person")

    if profile.email:
        eid = add_node(f"email:{profile.email}", profile.email, "Email")
        edges.append(GraphEdge(id=f"e-{person_id}-{eid}", source=person_id, target=eid, label="has email"))

    if profile.username:
        uid = add_node(f"user:{profile.username}", profile.username, "Username")
        edges.append(GraphEdge(id=f"e-{person_id}-{uid}", source=person_id, target=uid, label="has username"))

    if profile.phone:
        pid = add_node(f"phone:{profile.phone}", profile.phone, "Phone")
        edges.append(GraphEdge(id=f"e-{person_id}-{pid}", source=person_id, target=pid, label="has phone"))

    if profile.website:
        wid = add_node(f"web:{profile.website}", profile.website, "Website")
        edges.append(GraphEdge(id=f"e-{person_id}-{wid}", source=person_id, target=wid, label="has website"))

    if profile.location:
        lid = add_node(f"loc:{profile.location}", profile.location, "Location")
        edges.append(GraphEdge(id=f"e-{person_id}-{lid}", source=person_id, target=lid, label="located in"))

    for i, f in enumerate(findings):
        if not f.url and not f.platform:
            continue
        fid = add_node(
            f"finding:{i}",
            f.platform or f.title[:30],
            "PublicProfile" if f.category.value in ("username_discovery", "social_discovery") else "Finding",
            risk=f.risk_level.value,
            url=f.url,
            title=f.title,
            snippet=f.snippet,
            description=f.description,
            source=f.source,
            platform=f.platform,
            category=f.category.value,
        )
        parent = person_id
        if profile.username and f.category.value == "username_discovery":
            parent = f"user:{profile.username}"
        elif profile.email and f.category.value == "email_exposure":
            parent = f"email:{profile.email}"
        if parent in node_ids:
            edges.append(GraphEdge(id=f"ef-{i}", source=parent, target=fid, label=f.source))

    return GraphData(nodes=nodes, edges=edges)
