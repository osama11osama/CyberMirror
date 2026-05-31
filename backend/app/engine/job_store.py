"""Scan job progress tracking (in-memory)."""

from datetime import datetime
from typing import Any

_jobs: dict[str, dict[str, Any]] = {}


def create_job(scan_id: str, providers: list[str]) -> None:
    _jobs[scan_id] = {
        "scan_id": scan_id,
        "status": "running",
        "progress": 0,
        "total_providers": len(providers),
        "current_provider": "",
        "message": "Initializing scan…",
        "started_at": datetime.utcnow().isoformat(),
        "findings_so_far": 0,
    }


def update_job(scan_id: str, **kwargs: Any) -> None:
    if scan_id in _jobs:
        _jobs[scan_id].update(kwargs)


def complete_job(scan_id: str, finding_count: int) -> None:
    update_job(
        scan_id,
        status="completed",
        progress=100,
        message=f"Scan complete — {finding_count} findings",
        findings_so_far=finding_count,
    )


def fail_job(scan_id: str, error: str) -> None:
    update_job(scan_id, status="failed", message=error)


def get_job(scan_id: str) -> dict[str, Any] | None:
    return _jobs.get(scan_id)
