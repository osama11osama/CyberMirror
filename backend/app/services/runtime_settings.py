"""Persisted runtime settings (editable from UI)."""

import json

from app.config import PROJECT_ROOT, resolve_project_path, settings
from app.services.secrets import get_secret, migrate_plaintext_hibp, set_secret

RUNTIME_FILE = PROJECT_ROOT / "data" / "runtime_settings.json"

_ALL_MODULES = [
    "web_search", "username_scan", "social_browser", "email_scan",
    "phone_scan", "breach_scan", "domain_scan", "identity_correlator",
]

DEFAULTS = {
    "username_scan_limit": 600,
    "web_search_max_queries": 30,
    "web_search_results_per_query": 8,
    "wmn_data_path": str(settings.wmn_data_path),
    "playwright_enabled": True,
    "schedule_enabled": False,
    "schedule_interval_hours": 168,
    "cache_ttl_seconds": 3600,
    "enabled_modules": list(_ALL_MODULES),
    "locale": "en",
}


def load_runtime() -> dict:
    if not RUNTIME_FILE.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
        merged = dict(DEFAULTS)
        merged.update(data)
        if "hibp_api_key" in data and data["hibp_api_key"]:
            migrate_plaintext_hibp(data["hibp_api_key"])
            merged.pop("hibp_api_key", None)
            data.pop("hibp_api_key", None)
            save_runtime({k: v for k, v in data.items() if k != "hibp_api_key"})
        return merged
    except Exception:
        return dict(DEFAULTS)


def save_runtime(data: dict) -> dict:
    from app.modules.registry import DEFAULT_MODULES

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = load_runtime()
    if "hibp_api_key" in data:
        set_secret("hibp_api_key", data.pop("hibp_api_key") or None)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    if "enabled_modules" in merged:
        merged["enabled_modules"] = [
            m for m in merged["enabled_modules"] if m in DEFAULT_MODULES
        ] or list(DEFAULT_MODULES)
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
    settings.hibp_api_key = get_secret("hibp_api_key")
    settings.schedule_enabled = bool(data.get("schedule_enabled", False))
    settings.schedule_interval_hours = int(data.get("schedule_interval_hours", 168))
    wmn = data.get("wmn_data_path")
    if wmn:
        settings.wmn_data_path = resolve_project_path(wmn)


def get_enabled_modules() -> list[str]:
    from app.modules.registry import DEFAULT_MODULES

    rt = load_runtime()
    mods = rt.get("enabled_modules") or DEFAULT_MODULES
    return [m for m in mods if m in DEFAULT_MODULES] or list(DEFAULT_MODULES)
