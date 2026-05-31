"""Load platform definitions from WhatsMyName JSON (data only — our own checker)."""

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

SITES_FILE = Path(__file__).parent / "sites.json"

# Social platforms checked first — most relevant for username discovery.
PRIORITY_CATS = ("social", "coding", "media", "blog", "gaming", "messaging", "identity")


def _load_builtin() -> list[dict]:
    if not SITES_FILE.exists():
        return []
    return json.loads(SITES_FILE.read_text(encoding="utf-8"))


def _wmn_to_site(entry: dict) -> dict | None:
    uri = entry.get("uri_check") or entry.get("uri_pretty")
    if not uri or "{account}" not in uri:
        return None
    return {
        "name": entry["name"],
        "url": uri.replace("{account}", "{username}"),
        "category": entry.get("cat", "unknown"),
        "e_code": entry.get("e_code", 200),
        "e_string": entry.get("e_string", ""),
        "m_code": entry.get("m_code"),
        "m_string": entry.get("m_string", ""),
        # Legacy fields for built-in sites.json compatibility
        "exists_status": [entry.get("e_code", 200)],
        "missing_status": [entry.get("m_code")] if entry.get("m_code") else [404],
        "exists_text": entry.get("e_string", ""),
        "missing_text": entry.get("m_string", ""),
    }


def load_all_sites(limit: int | None = None) -> list[dict]:
    """Merge built-in sites with WMN database; built-in entries win on name clash."""
    limit = limit or settings.username_scan_limit
    by_name: dict[str, dict] = {}

    for site in _load_builtin():
        by_name[site["name"].lower()] = site

    wmn_path = settings.wmn_data_path
    if wmn_path.exists():
        try:
            data = json.loads(wmn_path.read_text(encoding="utf-8"))
            wmn_sites = data.get("sites", [])
            # Sort: priority categories first, then alphabetical
            def sort_key(s: dict) -> tuple:
                cat = s.get("cat", "zzz")
                pri = PRIORITY_CATS.index(cat) if cat in PRIORITY_CATS else 99
                return (pri, s.get("name", ""))

            wmn_sites.sort(key=sort_key)
            added = 0
            for entry in wmn_sites:
                if added >= limit:
                    break
                site = _wmn_to_site(entry)
                if not site:
                    continue
                key = site["name"].lower()
                if key not in by_name:
                    by_name[key] = site
                    added += 1
            logger.info("Loaded %d WMN sites from %s (limit %d)", added, wmn_path, limit)
        except Exception as exc:
            logger.warning("Could not load WMN data from %s: %s", wmn_path, exc)
    else:
        logger.info("WMN data not found at %s — using built-in sites only", wmn_path)

    return list(by_name.values())
