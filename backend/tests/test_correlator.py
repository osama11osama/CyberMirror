"""Tests for identity correlator."""

from app.models.schemas import Finding, IdentityProfile
from app.modules.identity.correlator import correlate_findings


def test_profile_only_correlations():
    profile = IdentityProfile(full_name="Jane Doe", username="janedoe", email="j@x.com")
    results = correlate_findings(profile, [], "scan-x")
    titles = {f.title for f in results}
    assert "Name + Username linked" in titles
    assert "Email + Real Name exposed" in titles


def test_cross_platform_correlation():
    profile = IdentityProfile(username="janedoe")
    existing = [
        Finding(platform="GitHub", url="https://github.com/janedoe", title="Profile"),
        Finding(platform="Twitter", url="https://twitter.com/janedoe", title="Profile"),
        Finding(platform="Reddit", url="https://reddit.com/u/janedoe", title="Profile"),
        Finding(platform="Instagram", url="https://instagram.com/janedoe", title="Profile"),
        Finding(platform="LinkedIn", url="https://linkedin.com/in/janedoe", title="Profile"),
    ]
    results = correlate_findings(profile, existing, "scan-y")
    assert any("5 platforms" in f.title for f in results)
