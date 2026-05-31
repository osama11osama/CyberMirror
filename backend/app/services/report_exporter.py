"""Report export service."""

import csv
import json
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.models.schemas import Finding, IdentityProfile, ScanSummary


def export_json(scan: ScanSummary, findings: list[Finding], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "scan": scan.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in findings],
        "exported_at": datetime.utcnow().isoformat(),
    }
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


def export_html(scan: ScanSummary, findings: list[Finding], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ""
    for f in findings:
        rows += f"""
        <tr>
          <td>{f.risk_level.value}</td>
          <td>{f.source}</td>
          <td>{f.platform}</td>
          <td><a href="{f.url}">{f.title}</a></td>
          <td>{f.risk_reason}</td>
          <td>{f.recommendation}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CyberMirror Report — {scan.id[:8]}</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; padding: 2rem; }}
    h1 {{ color: #58a6ff; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    th, td {{ border: 1px solid #30363d; padding: 8px; text-align: left; }}
    th {{ background: #161b22; }}
    tr:nth-child(even) {{ background: #161b22; }}
    .Critical {{ color: #ff6b6b; }} .High {{ color: #ffa657; }}
    .Medium {{ color: #f0c040; }} .Low {{ color: #3fb950; }}
  </style>
</head>
<body>
  <h1>CyberMirror Self-Audit Report</h1>
  <p><strong>Slogan:</strong> See Yourself as the Internet Sees You</p>
  <p>Scan ID: {scan.id} | Risk Score: {scan.risk_score} | Findings: {scan.finding_count}</p>
  <p>Generated: {datetime.utcnow().isoformat()} UTC</p>
  <table>
    <thead><tr>
      <th>Risk</th><th>Source</th><th>Platform</th><th>Finding</th>
      <th>Reason</th><th>Recommendation</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <footer style="margin-top:2rem;color:#8b949e;">
    For personal self-audit only. Data stays local.
  </footer>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")
    return path


def export_pdf(scan: ScanSummary, findings: list[Finding], path: Path) -> Path:
    """Generate real PDF from HTML report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    html_path = path.with_suffix(".html")
    export_html(scan, findings, html_path)
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
