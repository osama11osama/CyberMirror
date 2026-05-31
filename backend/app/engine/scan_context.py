"""Cooperative cancellation helpers for scan modules."""


class ScanCancelled(Exception):
    """Raised when a scan is cancelled mid-module."""


def check_cancelled(scan_id: str) -> bool:
    from app.engine.job_store import is_cancelled
    return bool(scan_id and is_cancelled(scan_id))


def raise_if_cancelled(scan_id: str) -> None:
    if check_cancelled(scan_id):
        raise ScanCancelled(f"Scan {scan_id[:8]} cancelled")
