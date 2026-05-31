"""Persisted runtime settings (editable from UI)."""

import json
from pathlib import Path

from app.config import PROJECT_ROOT, settings

RUNTIME_FILE = PROJECT_ROOT / "data" / "runtime_settings.json"

DEFAULTS = {
    "username_scan_limit": 600,
    "web_search_max_queries": 30,
    "web_search_results_per_query": 8,
    "wmn_data_path": str(settings.wmn_data_path),
    "playwright_enabled": True,
    "hibp_api_key": "",
    "schedule_enabled": False,
    "schedule_interval_hours": 168,
    "cache_ttl_seconds": 3600,
}


def load_runtime() -> dict:
    if not RUNTIME_FILE.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULTS)


def save_runtime(data: dict) -> dict:
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = load_runtime()
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    RUNTIME_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    apply_runtime(merged)
    return merged


def apply_runtime(data: dict | None = None) -> None:
    data = data or load_runtime()
    settings.username_scan_limit = int(data.get("username_scan_limit", 600))
    settings.web_search_max_queries = int(data.get("web_search_max_queries", 30))
    settings.web_search_results_per_query = int(data.get("web_search_results_per_query", 8))
    settings.cache_ttl_seconds = int(data.get("cache_ttl_seconds", 3600))
    settings.playwright_enabled = bool(data.get("playwright_enabled", True))
    settings.hibp_api_key = data.get("hibp_api_key") or None
    settings.schedule_enabled = bool(data.get("schedule_enabled", False))
    settings.schedule_interval_hours = int(data.get("schedule_interval_hours", 168))
    wmn = data.get("wmn_data_path")
    if wmn:
        settings.wmn_data_path = Path(wmn)
