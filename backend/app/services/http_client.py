"""HTTP helpers with retry logic."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.5,
) -> httpx.Response | None:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.get(url)
            if resp.status_code in (429, 503) and attempt < retries - 1:
                await asyncio.sleep(backoff * (attempt + 1))
                continue
            return resp
        except Exception as exc:
            last_exc = exc
            logger.debug("GET retry %s/%s for %s: %s", attempt + 1, retries, url, exc)
            if attempt < retries - 1:
                await asyncio.sleep(backoff * (attempt + 1))
    if last_exc:
        logger.debug("GET failed for %s: %s", url, last_exc)
    return None
