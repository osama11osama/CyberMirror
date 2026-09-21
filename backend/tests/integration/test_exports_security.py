"""Export integration: JSON/CSV/HTML escaping with isolated exports dir."""

from datetime import datetime, timezone

from app.models.schemas import Finding, FindingCategory, IdentityProfile, RiskLevel, ScanSummary
from app.services.report_exporter import export_csv, export_html, export_json


def test_exports_escape_and_write(isolated_app, tmp_path):
    _client, _headers = isolated_app
    scan = ScanSummary(
        id="exp1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        profile=IdentityProfile(username="janedoe"),
        status="completed",
        providers=["web_search"],
        finding_count=1,
        risk_score=10,
    )
    finding = Finding(
        source="web_search",
        platform="Web",
        title="<script>x</script>",
        url="https://example.com/p",
        category=FindingCategory.IDENTITY,
        risk_level=RiskLevel.LOW,
    )
    j = export_json(scan, [finding], tmp_path / "out.json")
    assert j.exists()
    c = export_csv([finding], tmp_path / "out.csv")
    assert c.exists()
    h = export_html(scan, [finding], tmp_path / "out.html")
    markup = h.read_text(encoding="utf-8")
    assert "<script>x</script>" not in markup
    assert "&lt;script&gt;" in markup
