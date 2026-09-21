"""Graph builder evidence-backed correlation tests."""

from app.models.evidence import VerificationState
from app.models.schemas import Finding, FindingCategory, FindingOutcome, IdentityProfile, RiskLevel
from app.services.graph_builder import build_graph


def test_seed_nodes_distinct_from_discovered():
    profile = IdentityProfile(username="jane", email="j@x.com")
    findings = [
        Finding(
            id="f1",
            platform="GitHub",
            url="https://github.com/jane",
            title="Profile",
            category=FindingCategory.USERNAME,
            source="username_scan",
            outcome=FindingOutcome.CONFIRMED,
            verification=VerificationState.VERIFIED,
            risk_level=RiskLevel.MEDIUM,
        ),
    ]
    graph = build_graph(profile, findings)
    seeds = [n for n in graph.nodes if n.data.get("role") == "seed"]
    discovered = [n for n in graph.nodes if n.data.get("role") == "discovered"]
    assert any(n.type == "Username" for n in seeds)
    assert discovered
    assert any(e.label == "search input" for e in graph.edges)


def test_multi_platform_handle_creates_correlation_node():
    profile = IdentityProfile(username="jane")
    findings = [
        Finding(
            id="a",
            platform="GitHub",
            url="https://github.com/jane",
            title="GH",
            category=FindingCategory.USERNAME,
            source="username_scan",
            outcome=FindingOutcome.CONFIRMED,
            verification=VerificationState.VERIFIED,
            risk_level=RiskLevel.MEDIUM,
        ),
        Finding(
            id="b",
            platform="Twitter",
            url="https://twitter.com/jane",
            title="TW",
            category=FindingCategory.SOCIAL,
            source="social_browser",
            outcome=FindingOutcome.CONFIRMED,
            verification=VerificationState.LIKELY,
            risk_level=RiskLevel.MEDIUM,
        ),
    ]
    graph = build_graph(profile, findings)
    corr = [n for n in graph.nodes if n.type == "Correlation" and n.id.startswith("corr-handle:")]
    assert len(corr) == 1
    assert any(e.label == "corroborates" for e in graph.edges)


def test_blocked_observation_is_weak_link_not_corroboration():
    profile = IdentityProfile(username="jane")
    findings = [
        Finding(
            id="b1",
            platform="Instagram",
            url="https://instagram.com/jane",
            title="Blocked",
            category=FindingCategory.SOCIAL,
            source="social_browser",
            outcome=FindingOutcome.INCONCLUSIVE,
            verification=VerificationState.BLOCKED,
            risk_level=RiskLevel.LOW,
        ),
        Finding(
            id="b2",
            platform="TikTok",
            url="https://tiktok.com/@jane",
            title="Also blocked",
            category=FindingCategory.SOCIAL,
            source="social_browser",
            outcome=FindingOutcome.INCONCLUSIVE,
            verification=VerificationState.BLOCKED,
            risk_level=RiskLevel.LOW,
        ),
    ]
    graph = build_graph(profile, findings)
    assert not any(n.id.startswith("corr-handle:") for n in graph.nodes)
    assert any(e.label == "weak / unverified" for e in graph.edges)
