"""Shared Have I Been Pwned API helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.cache import get_cached, set_cached
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)

HIBP_HEADERS = {"User-Agent": "CyberMirror-SelfAudit"}


@dataclass(frozen=True)
class HibpLookupResult:
    """Distinguish authoritative empty answers from request failures."""

    ok: bool
    items: list[dict]
    error: str | None = None


def hibp_headers() -> dict[str, str]:
    headers = dict(HIBP_HEADERS)
    if settings.hibp_api_key:
        headers["hibp-api-key"] = settings.hibp_api_key
    return headers


async def fetch_breaches(email: str) -> HibpLookupResult:
    if not settings.hibp_api_key:
        return HibpLookupResult(ok=False, items=[], error="missing_api_key")

    cache_key = f"hibp:breaches:{email}"
    cached = get_cached(cache_key)
    if cached is not None:
        return HibpLookupResult(ok=True, items=cached)

    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
    try:
        await throttle(1.5)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                url,
                headers=hibp_headers(),
                params={"truncateResponse": "false"},
            )
        if resp.status_code == 404:
            set_cached(cache_key, [])
            return HibpLookupResult(ok=True, items=[])
        if resp.status_code != 200:
            logger.warning("HIBP breaches status %s for %s", resp.status_code, email[:3] + "***")
            return HibpLookupResult(ok=False, items=[], error=f"http_{resp.status_code}")
        data = resp.json()
        if not isinstance(data, list):
            return HibpLookupResult(ok=False, items=[], error="malformed_json")
        set_cached(cache_key, data)
        return HibpLookupResult(ok=True, items=data)
    except Exception as exc:
        logger.warning("HIBP breaches error: %s", exc)
        return HibpLookupResult(ok=False, items=[], error="request_failed")


async def fetch_pastes(email: str) -> HibpLookupResult:
    if not settings.hibp_api_key:
        return HibpLookupResult(ok=False, items=[], error="missing_api_key")

    cache_key = f"hibp:pastes:{email}"
    cached = get_cached(cache_key)
    if cached is not None:
        return HibpLookupResult(ok=True, items=cached)

    url = f"https://haveibeenpwned.com/api/v3/pasteaccount/{email}"
    try:
        await throttle(1.5)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=hibp_headers())
        if resp.status_code == 404:
            set_cached(cache_key, [])
            return HibpLookupResult(ok=True, items=[])
        if resp.status_code != 200:
            logger.warning("HIBP pastes status %s for %s", resp.status_code, email[:3] + "***")
            return HibpLookupResult(ok=False, items=[], error=f"http_{resp.status_code}")
        data = resp.json()
        if not isinstance(data, list):
            return HibpLookupResult(ok=False, items=[], error="malformed_json")
        set_cached(cache_key, data)
        return HibpLookupResult(ok=True, items=data)
    except Exception as exc:
        logger.warning("HIBP pastes error: %s", exc)
        return HibpLookupResult(ok=False, items=[], error="request_failed")
