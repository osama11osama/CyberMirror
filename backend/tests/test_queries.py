"""Tests for query builder."""

from app.modules.identity.queries import build_queries, SITE_PLATFORMS


def test_build_queries_username_includes_site_searches():
    queries = build_queries({"username": "testuser", "full_name": "", "email": "", "phone": ""})
    assert any("site:facebook.com testuser" in q for q in queries)
    assert any('"testuser"' in q for q in queries)


def test_build_queries_phone():
    queries = build_queries({"phone": "+1234567890", "username": "", "full_name": "", "email": ""})
    assert any("+1234567890" in q for q in queries)


def test_site_platforms_not_empty():
    assert "facebook.com" in SITE_PLATFORMS
