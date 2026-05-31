"""Tests for in-memory job store."""

from app.engine.job_store import (
    append_live_findings,
    cancel_job,
    complete_job,
    create_job,
    get_live_findings,
    is_cancelled,
)


def test_create_and_complete_job():
    create_job("scan-1", ["web_search", "email_scan"])
    complete_job("scan-1", 5)
    from app.engine.job_store import get_job
    job = get_job("scan-1")
    assert job["status"] == "completed"
    assert job["findings_so_far"] == 5


def test_live_findings():
    create_job("scan-2", ["web_search"])
    append_live_findings("scan-2", [{"platform": "GitHub", "title": "hit"}])
    live = get_live_findings("scan-2")
    assert len(live) == 1
    assert live[0]["platform"] == "GitHub"


def test_cancel_job():
    create_job("scan-3", ["web_search"])
    assert cancel_job("scan-3") is True
    assert is_cancelled("scan-3") is True
