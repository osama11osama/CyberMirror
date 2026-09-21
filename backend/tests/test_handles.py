"""Safe profile-handle extraction."""

from app.services.handles import extract_profile_handle


def test_known_profile_hosts():
    assert extract_profile_handle("https://github.com/jane") == "jane"
    assert extract_profile_handle("https://twitter.com/jane") == "jane"
    assert extract_profile_handle("https://www.linkedin.com/in/jane-doe") == "jane-doe"
    assert extract_profile_handle("https://tiktok.com/@jane") == "jane"
    assert extract_profile_handle("https://www.reddit.com/user/jane") == "jane"


def test_generic_article_paths_are_not_handles():
    assert extract_profile_handle("https://site-a.example/articles/foo") is None
    assert extract_profile_handle("https://site-b.example/articles/bar") is None
    # Even on known hosts, skip reserved segments
    assert extract_profile_handle("https://github.com/articles") is None


def test_unknown_host_requires_seed_username_match():
    assert extract_profile_handle(
        "https://blog.example/jane", expected_username="jane"
    ) == "jane"
    assert extract_profile_handle(
        "https://blog.example/other", expected_username="jane"
    ) is None
    assert extract_profile_handle("https://blog.example/jane") is None


def test_required_profile_prefix_must_match():
    """Hosts with configured prefixes must not treat routing segments as handles."""
    assert extract_profile_handle("https://linkedin.com/groups/123") is None
    assert extract_profile_handle("https://www.linkedin.com/company/acme") is None
    assert extract_profile_handle("https://reddit.com/r/osint") is None
    assert extract_profile_handle("https://tiktok.com/foryou") is None
    assert extract_profile_handle("https://medium.com/tag/security") is None
    assert extract_profile_handle("https://facebook.com/groups/abc") is None
    # Valid prefixed profiles still work
    assert extract_profile_handle("https://linkedin.com/in/jane") == "jane"
    assert extract_profile_handle("https://reddit.com/u/jane") == "jane"
    assert extract_profile_handle("https://medium.com/@jane") == "jane"
