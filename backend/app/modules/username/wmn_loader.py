"""Load the local fallback catalog and optional WhatsMyName dataset.

CyberMirror does not vendor the upstream WhatsMyName dataset. When a user
provides wmn-data.json, its contents remain subject to the upstream
CC BY-SA 4.0 license. See THIRD_PARTY_NOTICES.md and ATTRIBUTION.md.
"""

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

SITES_FILE = Path(__file__).parent / "sites.json"

# Categories that are usually most useful in a self-audit are checked first.
PRIORITY_CATS = ("social", "coding", "media", "blog", "gaming", "messaging", "identity")


def _load_builtin() -> list[dict]:
    if not SITES_FILE.exists():
        return []
    return json.loads(SITES_FILE.read_text(encoding="utf-8"))


def _wmn_to_site(entry: dict) -> dict | None:
    """Normalize one WhatsMyName site entry for CyberMirror's checker."""
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
        "exists_status": [entry.get("e_code", 200)],
        "missing_status": [entry.get("m_code")] if entry.get("m_code") else [404],
        "exists_text": entry.get("e_string", ""),
        "missing_text": entry.get("m_string", ""),
    }


def load_all_sites(limit: int | None = None) -> list[dict]:
    """Merge fallback definitions with optional WMN data.

    The bundled fallback definitions win on a name collision so local fixes are
    deterministic. External WMN entries are normalized at runtime and are not
    copied into the repository.
    """
    limit = limit or settings.username_scan_limit
    by_name: dict[str, dict] = {}

    for site in _load_builtin():
        by_name[site["name"].lower()] = site

    wmn_path = settings.wmn_data_path
    if wmn_path.exists():
        try:
            data = json.loads(wmn_path.read_text(encoding="utf-8"))
            wmn_sites = data.get("sites", [])

            def sort_key(site: dict) -> tuple:
                category = site.get("cat", "zzz")
                priority = PRIORITY_CATS.index(category) if category in PRIORITY_CATS else 99
                return (priority, site.get("name", ""))

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
            logger.info("Loaded %d WMN sites (limit %d)", added, limit)
        except Exception as exc:
            logger.warning("Could not load configured WMN data: %s", exc)
    else:
        logger.info("WMN data not configured; using the fallback catalog")

    return list(by_name.values())


def wmn_status() -> dict:
    """Report optional WhatsMyName dataset availability."""
    path = settings.wmn_data_path
    if not path.exists():
        return {
            "loaded": False,
            "path": str(path),
            "site_count": 0,
            "message": "WMN data not found; using the fallback catalog",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = len(data.get("sites", []))
        return {
            "loaded": True,
            "path": str(path),
            "site_count": count,
            "message": f"{count} platforms in the configured WMN dataset",
        }
    except Exception as exc:
        return {
            "loaded": False,
            "path": str(path),
            "site_count": 0,
            "message": str(exc),
        }
