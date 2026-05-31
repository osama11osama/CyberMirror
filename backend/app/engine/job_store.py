"""Scan job progress tracking (in-memory)."""

from datetime import datetime
from typing import Any

_jobs: dict[str, dict[str, Any]] = {}
_cancelled: set[str] = set()
_live_findings: dict[str, list[dict]] = {}


def create_job(scan_id: str, providers: list[str]) -> None:
    _cancelled.discard(scan_id)
    _live_findings[scan_id] = []
    _jobs[scan_id] = {
        "scan_id": scan_id,
        "status": "running",
        "progress": 0,
        "total_providers": len(providers),
        "current_provider": "",
        "message": "Initializing scan…",
        "started_at": datetime.utcnow().isoformat(),
        "findings_so_far": 0,
        "modules_completed": 0,
        "module_errors": [],
    }


def update_job(scan_id: str, **kwargs: Any) -> None:
    if scan_id in _jobs:
        _jobs[scan_id].update(kwargs)


def append_live_findings(scan_id: str, findings: list) -> None:
    if scan_id not in _live_findings:
        _live_findings[scan_id] = []
    for f in findings:
        _live_findings[scan_id].append(f.model_dump() if hasattr(f, "model_dump") else f)


def get_live_findings(scan_id: str) -> list[dict]:
    return _live_findings.get(scan_id, [])


def complete_job(scan_id: str, finding_count: int) -> None:
    update_job(
        scan_id,
        status="completed",
        progress=100,
        message=f"Scan complete — {finding_count} findings",
        findings_so_far=finding_count,
    )
    _cancelled.discard(scan_id)


def fail_job(scan_id: str, error: str) -> None:
    update_job(scan_id, status="failed", message=error)
    _cancelled.discard(scan_id)


def cancel_job(scan_id: str) -> bool:
    if scan_id not in _jobs:
        return False
    _cancelled.add(scan_id)
    update_job(scan_id, status="cancelled", message="Scan cancelled by user")
    return True


def is_cancelled(scan_id: str) -> bool:
    return scan_id in _cancelled


def get_job(scan_id: str) -> dict[str, Any] | None:
    return _jobs.get(scan_id)


def add_module_error(scan_id: str, module_id: str, error: str) -> None:
    if scan_id in _jobs:
        errs = _jobs[scan_id].setdefault("module_errors", [])
        errs.append({"module": module_id, "error": error[:200]})
