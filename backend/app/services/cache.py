"""Simple file cache for web search results."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.config import settings

_CACHE_DIR = settings.cache_dir


def _key(query: str) -> Path:
    h = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:24]
    return _CACHE_DIR / f"{h}.json"


def get_cached(query: str, ttl_seconds: int | None = None) -> list[dict] | None:
    val = get_cached_raw(query, ttl_seconds)
    if val is None:
        return None
    return val if isinstance(val, list) else None


def get_cached_raw(query: str, ttl_seconds: int | None = None) -> Any | None:
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    path = _key(query)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("ts", 0) > ttl:
            path.unlink(missing_ok=True)
            return None
        return data.get("results") if "results" in data else data.get("value")
    except Exception:
        return None


def set_cached(query: str, results: list[dict]) -> None:
    set_cached_raw(query, results)


def set_cached_raw(key: str, value: Any) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _key(key).write_text(
        json.dumps({"ts": time.time(), "query": key, "value": value}),
        encoding="utf-8",
    )


def clear_cache() -> int:
    """Remove all cached search results. Returns count deleted."""
    if not _CACHE_DIR.exists():
        return 0
    count = 0
    for f in _CACHE_DIR.glob("*.json"):
        f.unlink(missing_ok=True)
        count += 1
    return count
