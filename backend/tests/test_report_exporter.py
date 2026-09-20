"""Regression tests for HTML/PDF report escaping."""

from datetime import datetime

from app.models.schemas import Finding, FindingCategory, IdentityProfile, RiskLevel, ScanSummary
from app.services.report_exporter import export_html, export_pdf, safe_report_href


def _scan() -> ScanSummary:
    return ScanSummary(
        id="scan-report-1",
        created_at=datetime(2026, 1, 1),
        profile=IdentityProfile(username="janedoe"),
        status="completed",
        providers=["web_search"],
        finding_count=1,
        risk_score=12.5,
    )


def _finding(**overrides) -> Finding:
    data = dict(
        source="web_search",
        platform="Web",
        title="Public listing",
        url="https://example.com/profile",
        category=FindingCategory.IDENTITY,
        risk_level=RiskLevel.MEDIUM,
        risk_reason="Exposed on a public page",
        recommendation="Review the listing",
    )
    data.update(overrides)
    return Finding(**data)


def test_safe_report_href_allows_http_https_only():
    assert safe_report_href("https://example.com/a") == "https://example.com/a"
    assert safe_report_href("http://example.com") == "http://example.com"
    assert safe_report_href("javascript:alert(1)") is None
    assert safe_report_href("data:text/html,<script>alert(1)</script>") is None
    assert safe_report_href("file:///etc/passwd") is None
    assert safe_report_href("") is None


def test_safe_report_href_rejects_malformed_urls(monkeypatch):
    def _boom(_raw):
        raise ValueError("Invalid IPv6 URL")

    monkeypatch.setattr("app.services.report_exporter.urlparse", _boom)
    assert safe_report_href("https://[") is None


def test_html_report_continues_when_url_parse_fails(tmp_path, monkeypatch):
    def _boom(_raw):
        raise ValueError("Invalid IPv6 URL")

    monkeypatch.setattr("app.services.report_exporter.urlparse", _boom)
    finding = _finding(title="Still exported", url="https://[")
    markup = export_html(_scan(), [finding], tmp_path / "malformed.html").read_text(encoding="utf-8")
    assert "Still exported" in markup
    assert "<a href=" not in markup


def test_html_report_escapes_script_title(tmp_path):
    finding = _finding(
        title="<script>alert(1)</script>",
        risk_reason='"><img src=x onerror=alert(1)>',
        recommendation="<b>owned</b>",
        source="<svg onload=alert(1)>",
        platform="GitHub</td><td>injected",
    )
    path = export_html(_scan(), [finding], tmp_path / "report.html")
    markup = path.read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in markup
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in markup
    assert "<img src=x onerror=alert(1)>" not in markup
    assert "&lt;b&gt;owned&lt;/b&gt;" in markup
    assert "<svg onload=alert(1)>" not in markup
    assert "GitHub&lt;/td&gt;&lt;td&gt;injected" in markup


def test_html_report_blocks_attribute_breaking_url(tmp_path):
    finding = _finding(url='https://evil.example" onclick="alert(1)')
    markup = export_html(_scan(), [finding], tmp_path / "attrs.html").read_text(encoding="utf-8")

    assert 'onclick="alert(1)"' not in markup
    assert "https://evil.example&quot; onclick=&quot;alert(1)" in markup


def test_html_report_does_not_link_javascript_url(tmp_path):
    finding = _finding(title="Click me", url="javascript:alert(1)")
    markup = export_html(_scan(), [finding], tmp_path / "js.html").read_text(encoding="utf-8")

    assert "javascript:alert(1)" not in markup
    assert "<a href=" not in markup
    assert "Click me" in markup


def test_pdf_export_uses_escaped_html(tmp_path):
    finding = _finding(title="<script>alert(1)</script>", url="javascript:alert(document.cookie)")
    pdf_path = export_pdf(_scan(), [finding], tmp_path / "report.pdf")
    html_path = pdf_path.with_suffix(".html")

    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    markup = html_path.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in markup
    assert "javascript:alert" not in markup
