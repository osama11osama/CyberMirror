"""Simple file cache for web search results."""

import hashlib
import json
import time
from pathlib import Path

from app.config import settings

_CACHE_DIR = settings.cache_dir


def _key(query: str) -> Path:
    h = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:24]
    return _CACHE_DIR / f"{h}.json"


def get_cached(query: str, ttl_seconds: int | None = None) -> list[dict] | None:
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    path = _key(query)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("ts", 0) > ttl:
            path.unlink(missing_ok=True)
            return None
        return data.get("results", [])
    except Exception:
        return None


def set_cached(query: str, results: list[dict]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _key(query).write_text(
        json.dumps({"ts": time.time(), "query": query, "results": results}),
        encoding="utf-8",
    )
