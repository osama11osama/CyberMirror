"""SQLite persistence for CyberMirror."""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.models.schemas import Finding, IdentityProfile, ScanSummary
from app.services.crypto import decrypt_text, encrypt_text
from app.services.timeutil import parse_iso_datetime, to_iso, utc_now_iso


def _store_profile(profile: IdentityProfile) -> str:
    return encrypt_text(profile.model_dump_json())


def _load_profile(raw: str) -> IdentityProfile:
    return IdentityProfile.model_validate_json(decrypt_text(raw))


def profile_from_row(row: dict | sqlite3.Row) -> IdentityProfile:
    return _load_profile(row["profile_json"])


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


def mark_orphaned_running_scans() -> int:
    """Mark in-progress scans as failed after a process restart (jobs are in-memory only)."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE scans SET status=? WHERE status=?",
            ("failed", "running"),
        )
        conn.commit()
        return cur.rowcount


def create_scan(profile: IdentityProfile, providers: list[str]) -> str:
    scan_id = str(uuid4())
    now = utc_now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scans (id, created_at, status, providers, profile_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scan_id, now, "running", json.dumps(providers), _store_profile(profile)),
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
                    to_iso(f.timestamp),
                    json.dumps({**(f.raw or {}), "outcome": f.outcome.value}),
                )
                for f in findings
            ],
        )
        conn.commit()


def list_scans(limit: int = 50, offset: int = 0) -> list[ScanSummary]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scans ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_row_to_summary(r) for r in rows]


def count_scans() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM scans").fetchone()
    return row["c"] if row else 0


def delete_scan(scan_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT id FROM scans WHERE id=?", (scan_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM findings WHERE scan_id=?", (scan_id,))
        conn.execute("DELETE FROM scans WHERE id=?", (scan_id,))
        conn.commit()
    return True


def delete_findings_for_scan(scan_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM findings WHERE scan_id=?", (scan_id,))
        conn.commit()


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
        created_at=parse_iso_datetime(row["created_at"]),
        profile=_load_profile(row["profile_json"]),
        status=row["status"],
        providers=json.loads(row["providers"]),
        finding_count=row["finding_count"],
        risk_score=row["risk_score"],
    )


def row_to_finding(row: dict) -> Finding:
    from app.models.schemas import FindingCategory, FindingOutcome, RiskLevel

    raw = json.loads(row["raw_json"] or "{}")
    outcome = FindingOutcome.UNKNOWN
    raw_outcome = raw.get("outcome")
    if isinstance(raw_outcome, str):
        try:
            outcome = FindingOutcome(raw_outcome)
        except ValueError:
            outcome = FindingOutcome.UNKNOWN

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
        outcome=outcome,
        timestamp=parse_iso_datetime(row["timestamp"]),
        raw=raw,
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


def risk_trends(limit: int = 20) -> list[dict]:
    """Recent scans for dashboard trend chart."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, risk_score, finding_count, status
            FROM scans WHERE status IN ('completed', 'cancelled')
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "risk_score": r["risk_score"],
            "finding_count": r["finding_count"],
            "status": r["status"],
        }
        for r in reversed(rows)
    ]
