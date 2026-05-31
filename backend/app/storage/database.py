"""SQLite persistence for CyberMirror."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.models.schemas import Finding, IdentityProfile, ScanSummary


def _connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                providers TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                risk_score REAL DEFAULT 0,
                finding_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                source TEXT,
                provider TEXT,
                category TEXT,
                platform TEXT,
                title TEXT,
                url TEXT,
                description TEXT,
                snippet TEXT,
                confidence REAL,
                risk_level TEXT,
                risk_reason TEXT,
                recommendation TEXT,
                timestamp TEXT,
                raw_json TEXT,
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                format TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            );
            """
        )
        conn.commit()


def create_scan(profile: IdentityProfile, providers: list[str]) -> str:
    scan_id = str(uuid4())
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scans (id, created_at, status, providers, profile_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scan_id, now, "running", json.dumps(providers), profile.model_dump_json()),
        )
        conn.commit()
    return scan_id


def update_scan_status(
    scan_id: str,
    status: str,
    finding_count: int = 0,
    risk_score: float = 0.0,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE scans SET status=?, finding_count=?, risk_score=? WHERE id=?
            """,
            (status, finding_count, risk_score, scan_id),
        )
        conn.commit()


def save_findings(findings: list[Finding]) -> None:
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO findings
            (id, scan_id, source, provider, category, platform, title, url,
             description, snippet, confidence, risk_level, risk_reason,
             recommendation, timestamp, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    f.id,
                    f.scan_id,
                    f.source,
                    f.provider,
                    f.category.value,
                    f.platform,
                    f.title,
                    f.url,
                    f.description,
                    f.snippet,
                    f.confidence,
                    f.risk_level.value,
                    f.risk_reason,
                    f.recommendation,
                    f.timestamp.isoformat(),
                    json.dumps(f.raw),
                )
                for f in findings
            ],
        )
        conn.commit()


def list_scans(limit: int = 50) -> list[ScanSummary]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scans ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_summary(r) for r in rows]


def get_scan(scan_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
        if not row:
            return None
        findings = conn.execute(
            "SELECT * FROM findings WHERE scan_id=? ORDER BY timestamp", (scan_id,)
        ).fetchall()
    return {"scan": dict(row), "findings": [dict(f) for f in findings]}


def _row_to_summary(row: sqlite3.Row) -> ScanSummary:
    return ScanSummary(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        profile=IdentityProfile.model_validate_json(row["profile_json"]),
        status=row["status"],
        providers=json.loads(row["providers"]),
        finding_count=row["finding_count"],
        risk_score=row["risk_score"],
    )


def row_to_finding(row: dict) -> Finding:
    from app.models.schemas import FindingCategory, RiskLevel

    return Finding(
        id=row["id"],
        scan_id=row["scan_id"],
        source=row["source"],
        provider=row["provider"],
        category=FindingCategory(row["category"]),
        platform=row["platform"],
        title=row["title"],
        url=row["url"],
        description=row["description"],
        snippet=row["snippet"],
        confidence=row["confidence"] or 0.0,
        risk_level=RiskLevel(row["risk_level"]),
        risk_reason=row["risk_reason"] or "",
        recommendation=row["recommendation"] or "",
        timestamp=datetime.fromisoformat(row["timestamp"]),
        raw=json.loads(row["raw_json"] or "{}"),
    )


def _finding_key(f: Finding) -> tuple[str, str]:
    return (f.url.lower().strip(), f.platform.lower())


def compare_scans(scan_a: str, scan_b: str):
    from app.models.schemas import ScanCompareResult

    data_a = get_scan(scan_a)
    data_b = get_scan(scan_b)
    if not data_a or not data_b:
        return None

    findings_a = [row_to_finding(f) for f in data_a["findings"]]
    findings_b = [row_to_finding(f) for f in data_b["findings"]]

    keys_a = {_finding_key(f): f for f in findings_a if f.url}
    keys_b = {_finding_key(f): f for f in findings_b if f.url}

    new = [keys_b[k] for k in keys_b if k not in keys_a]
    removed = [keys_a[k] for k in keys_a if k not in keys_b]
    unchanged = len(set(keys_a) & set(keys_b))

    return ScanCompareResult(
        scan_a=scan_a,
        scan_b=scan_b,
        new_findings=new,
        removed_findings=removed,
        unchanged_count=unchanged,
    )
