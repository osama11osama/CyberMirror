"""SQLite persistence for CyberMirror."""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.models.schemas import Finding, IdentityProfile, ScanSummary
from app.services.crypto import decrypt_text, encrypt_text
from app.services.timeutil import parse_iso_datetime, to_iso, utc_now_iso

# Bump when exposure scoring formula changes so legacy rows are backfilled once.
CURRENT_SCORING_VERSION = 1
_TERMINAL_SCAN_STATUSES = frozenset({"completed", "cancelled", "failed"})


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


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(scans)").fetchall()}
    if "scoring_version" not in cols:
        conn.execute(
            "ALTER TABLE scans ADD COLUMN scoring_version INTEGER NOT NULL DEFAULT 0"
        )
    if "intelligence_json" not in cols:
        conn.execute(
            "ALTER TABLE scans ADD COLUMN intelligence_json TEXT NOT NULL DEFAULT ''"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id)"
    )


def _row_scoring_version(row: sqlite3.Row | dict) -> int:
    try:
        return int(row["scoring_version"] or 0)
    except (KeyError, IndexError, TypeError):
        return 0


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
                finding_count INTEGER DEFAULT 0,
                scoring_version INTEGER NOT NULL DEFAULT 0
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
        _migrate_schema(conn)
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
            UPDATE scans
            SET status=?, finding_count=?, risk_score=?, scoring_version=?
            WHERE id=?
            """,
            (status, finding_count, risk_score, CURRENT_SCORING_VERSION, scan_id),
        )
        conn.commit()


def sync_risk_score(scan_id: str, findings: list[Finding], stored: float | None = None) -> float:
    """Recompute evidence-aware score and stamp scoring_version when needed.

    Findings are already loaded by callers (detail/dashboard/export); this persists
    the live score so History/trends can trust stored values after one backfill.
    Never persists while a scan is still running (avoids stamping a partial score).
    """
    from app.services.exposure_scoring import compute_risk_score

    score = float(compute_risk_score(findings))
    with _connect() as conn:
        row = conn.execute(
            "SELECT risk_score, scoring_version, status FROM scans WHERE id=?",
            (scan_id,),
        ).fetchone()
        if not row:
            return score
        if row["status"] not in _TERMINAL_SCAN_STATUSES:
            return score
        stored_score = float(stored) if stored is not None else float(row["risk_score"] or 0)
        version = _row_scoring_version(row)
        if version < CURRENT_SCORING_VERSION:
            cur = conn.execute(
                """
                UPDATE scans SET risk_score=?, scoring_version=?
                WHERE id=? AND scoring_version < ?
                """,
                (score, CURRENT_SCORING_VERSION, scan_id, CURRENT_SCORING_VERSION),
            )
            conn.commit()
            if cur.rowcount == 0:
                latest = conn.execute(
                    "SELECT risk_score FROM scans WHERE id=?", (scan_id,)
                ).fetchone()
                return float(latest["risk_score"] or 0) if latest else score
        elif abs(stored_score - score) > 0.05:
            conn.execute(
                "UPDATE scans SET risk_score=? WHERE id=? AND scoring_version=?",
                (score, scan_id, CURRENT_SCORING_VERSION),
            )
            conn.commit()
    return score


def _backfill_scan_score(
    conn: sqlite3.Connection,
    scan_id: str,
    *,
    status: str,
    stored_score: float,
) -> float:
    """One-time recompute for a legacy terminal row; stamps CURRENT_SCORING_VERSION.

    Skips nonterminal scans. Uses a version-gated UPDATE so a concurrent completion
    that already stamped the current version is not overwritten with a stale score.
    """
    from app.services.exposure_scoring import compute_risk_score

    if status not in _TERMINAL_SCAN_STATUSES:
        return float(stored_score)

    finding_rows = conn.execute(
        "SELECT * FROM findings WHERE scan_id=? ORDER BY timestamp",
        (scan_id,),
    ).fetchall()
    findings = [row_to_finding(dict(f)) for f in finding_rows]
    score = float(compute_risk_score(findings))
    cur = conn.execute(
        """
        UPDATE scans SET risk_score=?, scoring_version=?
        WHERE id=? AND scoring_version < ?
        """,
        (score, CURRENT_SCORING_VERSION, scan_id, CURRENT_SCORING_VERSION),
    )
    if cur.rowcount == 0:
        row = conn.execute(
            "SELECT risk_score FROM scans WHERE id=?", (scan_id,)
        ).fetchone()
        return float(row["risk_score"] or 0) if row else score
    return score


def _finding_raw_payload(f: Finding) -> dict:
    payload = {**(f.raw or {}), "outcome": f.outcome.value}
    if f.verification:
        payload["verification"] = f.verification.value
    if f.evidence is not None:
        payload["evidence"] = f.evidence.model_dump(mode="json")
    return payload


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
                    json.dumps(_finding_raw_payload(f)),
                )
                for f in findings
            ],
        )
        conn.commit()


def save_intelligence(scan_id: str, payload: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE scans SET intelligence_json=? WHERE id=?",
            (json.dumps(payload), scan_id),
        )
        conn.commit()


def load_intelligence(scan_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT intelligence_json FROM scans WHERE id=?", (scan_id,)
        ).fetchone()
    if not row:
        return None
    raw = row["intelligence_json"] or ""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def redact_intelligence_artifacts(scan_id: str) -> int:
    """Clear captured page text from persisted intelligence payloads.

    File-cache deletion alone is insufficient because PageArtifact.main_text is
    also stored in scans.intelligence_json. Persist whenever main_text,
    metadata body fields, or the redaction marker change — not only when
    main_text was nonempty.
    """
    payload = load_intelligence(scan_id)
    if not payload:
        return 0
    changed = 0
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        for art in artifacts:
            if not isinstance(art, dict):
                continue
            mutated = False
            if art.get("main_text"):
                art["main_text"] = ""
                mutated = True
            meta = art.get("metadata")
            if isinstance(meta, dict):
                # Drop bulky nested copies; keep provenance ids/status.
                for key in ("raw_html", "body"):
                    if key in meta:
                        meta.pop(key, None)
                        mutated = True
            if not art.get("content_redacted"):
                art["content_redacted"] = True
                mutated = True
            if mutated:
                changed += 1
    if changed:
        save_intelligence(scan_id, payload)
    return changed


def list_scans(limit: int = 50, offset: int = 0) -> list[ScanSummary]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scans ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        out: list[ScanSummary] = []
        dirty = False
        for r in rows:
            if _row_scoring_version(r) >= CURRENT_SCORING_VERSION:
                out.append(_row_to_summary(r))
                continue
            if r["status"] not in _TERMINAL_SCAN_STATUSES:
                out.append(_row_to_summary(r))
                continue
            score = _backfill_scan_score(
                conn,
                r["id"],
                status=r["status"],
                stored_score=float(r["risk_score"] or 0),
            )
            dirty = True
            out.append(_row_to_summary(r, risk_score=score))
        if dirty:
            conn.commit()
    return out


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


def _row_to_summary(row: sqlite3.Row, *, risk_score: float | None = None) -> ScanSummary:
    return ScanSummary(
        id=row["id"],
        created_at=parse_iso_datetime(row["created_at"]),
        profile=_load_profile(row["profile_json"]),
        status=row["status"],
        providers=json.loads(row["providers"]),
        finding_count=row["finding_count"],
        risk_score=float(row["risk_score"] if risk_score is None else risk_score),
    )


def row_to_finding(row: dict) -> Finding:
    from app.models.evidence import EvidenceObservation, VerificationState
    from app.models.schemas import FindingCategory, FindingOutcome, RiskLevel

    raw = json.loads(row["raw_json"] or "{}")
    outcome = FindingOutcome.UNKNOWN
    raw_outcome = raw.get("outcome")
    if isinstance(raw_outcome, str):
        try:
            outcome = FindingOutcome(raw_outcome)
        except ValueError:
            outcome = FindingOutcome.UNKNOWN

    verification = VerificationState.UNKNOWN
    raw_verification = raw.get("verification")
    if isinstance(raw_verification, str):
        try:
            verification = VerificationState(raw_verification)
        except ValueError:
            verification = VerificationState.UNKNOWN

    evidence = None
    raw_evidence = raw.get("evidence")
    if isinstance(raw_evidence, dict):
        try:
            evidence = EvidenceObservation.model_validate(raw_evidence)
            if verification == VerificationState.UNKNOWN and evidence.verification:
                verification = evidence.verification
        except Exception:
            evidence = None

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
        verification=verification,
        evidence=evidence,
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
    """Recent scans for dashboard trend chart (cached evidence-aware scores)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, risk_score, finding_count, status, scoring_version
            FROM scans WHERE status IN ('completed', 'cancelled')
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict] = []
        dirty = False
        for r in rows:
            if _row_scoring_version(r) >= CURRENT_SCORING_VERSION:
                score = float(r["risk_score"] or 0)
            else:
                score = _backfill_scan_score(
                    conn,
                    r["id"],
                    status=r["status"],
                    stored_score=float(r["risk_score"] or 0),
                )
                dirty = True
            out.append(
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "risk_score": score,
                    "finding_count": r["finding_count"],
                    "status": r["status"],
                }
            )
        if dirty:
            conn.commit()
    return list(reversed(out))
