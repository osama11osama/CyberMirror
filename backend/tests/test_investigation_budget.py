"""Investigation budget and responsible-use guardrails (#44)."""

from app.services.investigation_budget import (
    FORBIDDEN_CAPABILITIES,
    default_budget,
    delete_deep_artifacts,
    deep_artifacts_dir,
    get_budget,
)


def test_query_and_page_budgets():
    b = default_budget("scan-1")
    b.max_generated_queries = 2
    b.max_pages_total = 2
    b.max_pages_per_domain = 1
    assert b.consume_query() is None
    assert b.consume_query() is None
    assert b.consume_query() == "query_budget_exhausted"
    assert b.consume_page("https://a.example/x") is None
    assert b.consume_page("https://a.example/y") == "domain_page_budget_exhausted"
    assert b.consume_page("https://b.example/z") is None
    assert b.consume_page("https://c.example/z") == "page_budget_exhausted"


def test_cancellation_stops_work():
    b = default_budget("scan-2")
    b.cancel()
    assert b.check_continue() == "cancelled"
    assert b.consume_query() == "cancelled"
    assert b.consume_page("https://x.example/") == "cancelled"


def test_blocked_backoff():
    b = default_budget("scan-3")
    b.max_blocked_hits_before_stop = 2
    assert b.record_blocked("https://hard.example/p") is None
    assert b.record_blocked("https://hard.example/p") == "domain_blocked_backoff"
    assert b.consume_page("https://hard.example/q") == "domain_blocked_backoff"


def test_content_cap_and_forbidden_docs():
    b = default_budget("scan-4")
    b.max_extracted_content_bytes = 10
    assert len(b.cap_content("abcdefghijklmnop").encode()) <= 10
    assert any("CAPTCHA" in x or "captcha" in x.lower() for x in FORBIDDEN_CAPABILITIES)
    assert get_budget("scan-4") is b


def test_delete_deep_artifacts(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_dir", tmp_path)
    scan_id = "123e4567-e89b-12d3-a456-426614174000"
    root = deep_artifacts_dir(scan_id)
    root.mkdir(parents=True)
    f = root / "page.txt"
    f.write_text("excerpt", encoding="utf-8")
    assert delete_deep_artifacts(scan_id) == 1
    assert not f.exists()
