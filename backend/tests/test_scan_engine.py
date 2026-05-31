"""Tests for finding deduplication."""

from app.engine.scan_engine import dedupe_findings
from app.models.schemas import Finding


def test_dedupe_by_url_and_platform():
    findings = [
        Finding(platform="GitHub", url="https://github.com/u", title="a"),
        Finding(platform="GitHub", url="https://github.com/u", title="b"),
        Finding(platform="GitLab", url="https://gitlab.com/u", title="c"),
    ]
    result = dedupe_findings(findings)
    assert len(result) == 2


def test_no_url_findings_kept():
    findings = [
        Finding(platform="Summary", url="", title="x"),
        Finding(platform="Summary", url="", title="y"),
    ]
    assert len(dedupe_findings(findings)) == 2
