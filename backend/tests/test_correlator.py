"""Tests for identity correlator."""

from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile, RiskLevel
from app.models.evidence import VerificationState
from app.modules.identity.correlator import correlate_findings
from app.services.graph_builder import build_graph
from app.services.risk_engine import analyze_finding


def test_input_only_fields_are_not_public_exposure():
    profile = IdentityProfile(
        full_name="Jane Doe",
        username="janedoe",
        email="j@x.com",
        phone="+15550100",
        location="Berlin",
    )
    results = correlate_findings(profile, [], "scan-x")
    assert results == []


def test_evidence_backed_name_username_correlation():
    profile = IdentityProfile(full_name="Jane Doe", username="janedoe", location="Berlin")
    existing = [
        Finding(
            id="f1",
            platform="Web",
            title="Jane Doe uses janedoe online",
            url="https://example.com/janedoe",
            snippet="Profile for Jane Doe (@janedoe)",
            source="web_search",
            category=FindingCategory.IDENTITY,
            outcome=FindingOutcome.CONFIRMED,
            verification=VerificationState.VERIFIED,
        ),
    ]
    results = correlate_findings(profile, existing, "scan-y")
    assert any("Name + Username linked in public results" in f.title for f in results)
    hit = next(f for f in results if "Name + Username" in f.title)
    assert hit.outcome == FindingOutcome.CONFIRMED
    assert hit.raw.get("evidence_backed") is True
    assert "f1" in hit.raw.get("supporting_finding_ids", [])
    assert "Berlin" not in (hit.snippet or "")
    assert "Jane Doe" in hit.snippet and "janedoe" in hit.snippet


def test_search_query_description_is_not_observed_evidence():
    """Web search findings embed the query in description — that must not invent co-mentions."""
    profile = IdentityProfile(full_name="Jane Doe", username="janedoe", email="jane@example.com")
    existing = [
        Finding(
            id="q1",
            platform="Web",
            title="Unrelated article about widgets",
            description='Found via search: "Jane Doe" janedoe',
            url="https://example.com/widgets",
            snippet="How to build better widgets in 2026",
            source="web_search",
            category=FindingCategory.IDENTITY,
        ),
    ]
    results = correlate_findings(profile, existing, "scan-q")
    assert not any("Name + Username linked" in f.title for f in results)
    assert not any("Email + Real Name linked" in f.title for f in results)


def test_cross_platform_correlation():
    profile = IdentityProfile(username="janedoe")
    existing = [
        Finding(
            platform=p, url=u, title="Profile",
            outcome=FindingOutcome.CONFIRMED,
            verification=VerificationState.VERIFIED,
            category=FindingCategory.USERNAME,
            source="username_scan",
        )
        for p, u in (
            ("GitHub", "https://github.com/janedoe"),
            ("Twitter", "https://twitter.com/janedoe"),
            ("Reddit", "https://reddit.com/u/janedoe"),
            ("Instagram", "https://instagram.com/janedoe"),
            ("LinkedIn", "https://linkedin.com/in/janedoe"),
        )
    ]
    results = correlate_findings(profile, existing, "scan-y")
    assert any("5 platforms" in f.title for f in results)


def test_possible_http200_findings_do_not_confirm_platform_count():
    """Status-only POSSIBLE hits must not produce a CONFIRMED multi-platform claim."""
    profile = IdentityProfile(username="janedoe")
    existing = [
        Finding(
            id=f"p{i}",
            platform=name,
            url=f"https://{name.lower()}.example.com/janedoe",
            title=f"Possible account: {name}",
            category=FindingCategory.USERNAME,
            source="username_scan",
            outcome=FindingOutcome.INCONCLUSIVE,
            verification=VerificationState.POSSIBLE,
        )
        for i, name in enumerate(
            ("SiteA", "SiteB", "SiteC", "SiteD", "SiteE", "SiteF")
        )
    ]
    results = correlate_findings(profile, existing, "scan-possible")
    assert not any("platforms" in f.title.lower() for f in results)
    assert not any(f.outcome == FindingOutcome.CONFIRMED for f in results)


def test_graph_marks_seed_attributes_separately_from_findings():
    profile = IdentityProfile(full_name="Jane Doe", username="janedoe", email="j@x.com")
    findings = [
        Finding(
            platform="GitHub",
            url="https://github.com/janedoe",
            title="Profile",
            category=FindingCategory.USERNAME,
            source="username_scan",
        ),
    ]
    graph = build_graph(profile, findings)
    seed_nodes = [n for n in graph.nodes if n.data.get("role") == "seed"]
    discovered = [n for n in graph.nodes if n.data.get("role") == "discovered"]
    assert any(n.type == "Email" for n in seed_nodes)
    assert any(n.type == "Username" for n in seed_nodes)
    assert discovered
    assert any(e.label == "search input" for e in graph.edges)


def test_legacy_seed_correlation_is_not_high_risk():
    f = Finding(
        source="identity_correlator",
        platform="Correlation Engine",
        title="Email + Real Name exposed",
        category=FindingCategory.IDENTITY,
        description="High risk — real identity tied to email in public results",
    )
    analyze_finding(f, IdentityProfile(full_name="Jane", email="j@x.com"))
    assert f.risk_level == RiskLevel.INFO
    assert f.outcome == FindingOutcome.SYSTEM
