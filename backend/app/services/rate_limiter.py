"""Global async rate limiting for outbound HTTP/search calls."""

import asyncio
import time

_lock = asyncio.Lock()
_last_call = 0.0
_min_interval = 0.35


async def throttle(delay: float | None = None) -> None:
    """Ensure minimum gap between outbound requests across modules."""
    global _last_call
    gap = delay if delay is not None else _min_interval
    async with _lock:
        now = time.monotonic()
        wait = gap - (now - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
