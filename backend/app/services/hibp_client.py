"""Shared Have I Been Pwned API helpers."""

import logging

import httpx

from app.config import settings
from app.services.cache import get_cached, set_cached
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)

HIBP_HEADERS = {"User-Agent": "CyberMirror-SelfAudit"}


def hibp_headers() -> dict[str, str]:
    headers = dict(HIBP_HEADERS)
    if settings.hibp_api_key:
        headers["hibp-api-key"] = settings.hibp_api_key
    return headers


async def fetch_breaches(email: str) -> list[dict]:
    if not settings.hibp_api_key:
        return []

    cache_key = f"hibp:breaches:{email}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

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
            return []
        if resp.status_code != 200:
            logger.warning("HIBP breaches status %s for %s", resp.status_code, email[:3] + "***")
            return []
        data = resp.json()
        set_cached(cache_key, data)
        return data
    except Exception as exc:
        logger.warning("HIBP breaches error: %s", exc)
        return []


async def fetch_pastes(email: str) -> list[dict]:
    if not settings.hibp_api_key:
        return []

    cache_key = f"hibp:pastes:{email}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"https://haveibeenpwned.com/api/v3/pasteaccount/{email}"
    try:
        await throttle(1.5)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=hibp_headers())
        if resp.status_code == 404:
            set_cached(cache_key, [])
            return []
        if resp.status_code != 200:
            logger.warning("HIBP pastes status %s for %s", resp.status_code, email[:3] + "***")
            return []
        data = resp.json()
        set_cached(cache_key, data)
        return data
    except Exception as exc:
        logger.warning("HIBP pastes error: %s", exc)
        return []
