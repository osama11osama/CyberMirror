"""Investigation scope, collection budgets, and responsible crawling (#44)."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings


# Explicitly out of scope — documented for contributors and enforced by absence.
FORBIDDEN_CAPABILITIES = (
    "authentication bypass",
    "CAPTCHA bypass",
    "paywall / access-control bypass",
    "credential stuffing",
    "scraping private/non-public account areas",
    "aggressive retry against blocked services",
)


@dataclass
class InvestigationBudget:
    """Central budget consumed by search, acquisition, and pivot code."""

    scan_id: str
    max_pivot_depth: int = 2
    max_generated_queries: int = 40
    max_pages_total: int = 60
    max_pages_per_domain: int = 8
    max_extracted_content_bytes: int = 400_000
    page_timeout_seconds: float = 20.0
    allowed_domains: set[str] | None = None  # None = unrestricted public
    blocked_domains: set[str] = field(default_factory=set)
    cancelled: bool = False

    queries_used: int = 0
    pages_used: int = 0
    pages_by_domain: dict[str, int] = field(default_factory=dict)
    blocked_hits_by_domain: dict[str, int] = field(default_factory=dict)
    max_blocked_hits_before_stop: int = 3

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True

    def is_cancelled(self) -> bool:
        with self._lock:
            return self.cancelled

    def check_continue(self) -> str | None:
        """Return a stop reason, or None if work may continue."""
        with self._lock:
            if self.cancelled:
                return "cancelled"
            if self.queries_used >= self.max_generated_queries:
                return "query_budget_exhausted"
            if self.pages_used >= self.max_pages_total:
                return "page_budget_exhausted"
            return None

    def allow_domain(self, host: str) -> bool:
        host = (host or "").lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        if host in self.blocked_domains:
            return False
        if self.allowed_domains is not None and host not in self.allowed_domains:
            return False
        return True

    def consume_query(self) -> str | None:
        with self._lock:
            if self.cancelled:
                return "cancelled"
            if self.queries_used >= self.max_generated_queries:
                return "query_budget_exhausted"
            self.queries_used += 1
            return None

    def consume_page(self, url: str) -> str | None:
        host = urlparse(url).netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        with self._lock:
            if self.cancelled:
                return "cancelled"
            if not self.allow_domain(host):
                return "domain_not_allowed"
            if self.pages_used >= self.max_pages_total:
                return "page_budget_exhausted"
            used = self.pages_by_domain.get(host, 0)
            if used >= self.max_pages_per_domain:
                return "domain_page_budget_exhausted"
            if self.blocked_hits_by_domain.get(host, 0) >= self.max_blocked_hits_before_stop:
                return "domain_blocked_backoff"
            self.pages_used += 1
            self.pages_by_domain[host] = used + 1
            return None

    def record_blocked(self, url: str) -> str | None:
        """Record a blocked/challenge response; stop after repeated hits."""
        host = urlparse(url).netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        with self._lock:
            n = self.blocked_hits_by_domain.get(host, 0) + 1
            self.blocked_hits_by_domain[host] = n
            if n >= self.max_blocked_hits_before_stop:
                return "domain_blocked_backoff"
            return None

    def cap_content(self, text: str) -> str:
        raw = text or ""
        encoded = raw.encode("utf-8", errors="ignore")
        if len(encoded) <= self.max_extracted_content_bytes:
            return raw
        return encoded[: self.max_extracted_content_bytes].decode("utf-8", errors="ignore")

    def as_dict(self) -> dict:
        with self._lock:
            return {
                "scan_id": self.scan_id,
                "max_pivot_depth": self.max_pivot_depth,
                "max_generated_queries": self.max_generated_queries,
                "max_pages_total": self.max_pages_total,
                "max_pages_per_domain": self.max_pages_per_domain,
                "max_extracted_content_bytes": self.max_extracted_content_bytes,
                "page_timeout_seconds": self.page_timeout_seconds,
                "queries_used": self.queries_used,
                "pages_used": self.pages_used,
                "pages_by_domain": dict(self.pages_by_domain),
                "blocked_hits_by_domain": dict(self.blocked_hits_by_domain),
                "cancelled": self.cancelled,
                "forbidden_capabilities": list(FORBIDDEN_CAPABILITIES),
            }


_budgets: dict[str, InvestigationBudget] = {}
_budgets_lock = threading.Lock()


def default_budget(scan_id: str) -> InvestigationBudget:
    """Create and register the sole active budget for an investigation.

    The former ``allowed_seed_identifiers`` field was removed because no
    production stage enforced it; retaining it implied a scope boundary that
    did not exist.  Scope is represented by the explicit profile passed to the
    query planner, while this object enforces operational limits.
    """
    budget = InvestigationBudget(scan_id=scan_id)
    with _budgets_lock:
        _budgets[scan_id] = budget
    return budget


def get_budget(scan_id: str) -> InvestigationBudget | None:
    with _budgets_lock:
        return _budgets.get(scan_id)


def clear_budget(scan_id: str) -> None:
    with _budgets_lock:
        _budgets.pop(scan_id, None)


def deep_artifacts_dir(scan_id: str | None = None) -> Path:
    base = (settings.cache_dir / "deep_artifacts").resolve()
    if not scan_id:
        return base
    safe_id = validate_artifact_scan_id(scan_id)
    root = (base / safe_id).resolve()
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise ValueError("artifact path escapes deep_artifacts root") from exc
    return root


_SCAN_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def validate_artifact_scan_id(scan_id: str) -> str:
    """Reject path traversal / non-UUID scan identifiers used for artifact paths."""
    value = (scan_id or "").strip()
    if not _SCAN_ID_RE.fullmatch(value):
        raise ValueError("scan_id must be a UUID")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError("invalid scan_id")
    return value


def list_deep_artifacts(scan_id: str) -> list[dict]:
    root = deep_artifacts_dir(scan_id)
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append({"path": str(p.relative_to(root)), "bytes": p.stat().st_size})
    return out


def delete_deep_artifacts(scan_id: str | None = None) -> int:
    """Delete locally stored deep-analysis artifacts. Returns files removed.

    When ``scan_id`` is set it must be a UUID; bulk delete (None) only clears
    the deep_artifacts root itself, never a parent directory.
    """
    if scan_id is None:
        root = (settings.cache_dir / "deep_artifacts").resolve()
        base = root
    else:
        root = deep_artifacts_dir(scan_id)
        base = (settings.cache_dir / "deep_artifacts").resolve()
        try:
            root.relative_to(base)
        except ValueError:
            return 0
    if not root.exists():
        return 0
    removed = 0
    for p in sorted(root.rglob("*"), reverse=True):
        # Never follow a resolved path outside the artifacts base.
        try:
            p.resolve().relative_to(base)
        except ValueError:
            continue
        if p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
        elif p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    return removed
