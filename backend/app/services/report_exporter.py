"""Report export service."""

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.models.schemas import Finding, ScanSummary
from app.services.timeutil import utc_now_iso

_ALLOWED_HREF_SCHEMES = {"http", "https"}


def _html(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def safe_report_href(url: str) -> str | None:
    """Return an escaped http(s) href, or None for empty/unsafe URLs."""
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _ALLOWED_HREF_SCHEMES or not parsed.netloc:
        return None
    return _html(raw)


def _finding_link(finding: Finding) -> str:
    title = _html(finding.title)
    href = safe_report_href(finding.url)
    if href:
        return f'<a href="{href}">{title}</a>'
    return title


def export_json(
    scan: ScanSummary,
    findings: list[Finding],
    path: Path,
    *,
    intelligence: dict | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "scan": scan.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in findings],
        "exported_at": utc_now_iso(),
    }
    if intelligence:
        from app.services.intelligence_report import build_intelligence_summary

        data["intelligence"] = intelligence
        data["intelligence_summary"] = build_intelligence_summary(intelligence)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_csv(findings: list[Finding], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source", "platform", "title", "url", "category",
        "risk_level", "risk_reason", "recommendation", "confidence",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for finding in findings:
            writer.writerow({k: getattr(finding, k, "") for k in fields})
    return path


def export_html(
    scan: ScanSummary,
    findings: list[Finding],
    path: Path,
    *,
    intelligence: dict | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ""
    for f in findings:
        rows += f"""
        <tr>
          <td>{_html(f.risk_level.value)}</td>
          <td>{_html(f.source)}</td>
          <td>{_html(f.platform)}</td>
          <td>{_finding_link(f)}</td>
          <td>{_html(f.risk_reason)}</td>
          <td>{_html(f.recommendation)}</td>
        </tr>"""

    intel_html = ""
    if intelligence:
        from app.services.intelligence_report import intelligence_html_section

        intel_html = intelligence_html_section(intelligence)

    markup = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CyberMirror Report — {_html(scan.id[:8])}</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; padding: 2rem; }}
    h1 {{ color: #58a6ff; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    th, td {{ border: 1px solid #30363d; padding: 8px; text-align: left; }}
    th {{ background: #161b22; }}
    tr:nth-child(even) {{ background: #161b22; }}
    .Critical {{ color: #ff6b6b; }} .High {{ color: #ffa657; }}
    .Medium {{ color: #f0c040; }} .Low {{ color: #3fb950; }}
    .intelligence-report {{ margin-top: 2rem; border-top: 1px solid #30363d; padding-top: 1rem; }}
  </style>
</head>
<body>
  <h1>CyberMirror Self-Audit Report</h1>
  <p><strong>Slogan:</strong> See Yourself as the Internet Sees You</p>
  <p>Scan ID: {_html(scan.id)} | Risk Score: {_html(scan.risk_score)} | Findings: {_html(scan.finding_count)}</p>
  <p>Generated: {_html(utc_now_iso())} UTC</p>
  <table>
    <thead><tr>
      <th>Risk</th><th>Source</th><th>Platform</th><th>Finding</th>
      <th>Reason</th><th>Recommendation</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {intel_html}
  <footer style="margin-top:2rem;color:#8b949e;">
    For personal self-audit only. Data stays local.
  </footer>
</body>
</html>"""
    path.write_text(markup, encoding="utf-8")
    return path


def export_pdf(
    scan: ScanSummary,
    findings: list[Finding],
    path: Path,
    *,
    intelligence: dict | None = None,
) -> Path:
    """Generate real PDF from HTML report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    html_path = path.with_suffix(".html")
    export_html(scan, findings, html_path, intelligence=intelligence)
    html = html_path.read_text(encoding="utf-8")
    try:
        from xhtml2pdf import pisa
        with path.open("wb") as pdf_file:
            status = pisa.CreatePDF(html, dest=pdf_file, encoding="utf-8")
        if status.err:
            raise RuntimeError(f"PDF generation errors: {status.err}")
    except ImportError as exc:
        raise RuntimeError("Install xhtml2pdf: pip install xhtml2pdf") from exc
    return path
