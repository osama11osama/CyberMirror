"""Background scheduled scan loop."""

import asyncio
import logging
from datetime import datetime, timedelta

from app.config import settings
from app.engine.scan_engine import ScanEngine
from app.models.schemas import IdentityProfile
from app.modules.registry import DEFAULT_MODULES
from app.services.runtime_settings import load_runtime
from app.storage.database import list_scans

logger = logging.getLogger(__name__)

_engine = ScanEngine()
_task: asyncio.Task | None = None
_last_run: datetime | None = None


async def _scheduler_loop() -> None:
    global _last_run
    while True:
        await asyncio.sleep(60)
        rt = load_runtime()
        if not rt.get("schedule_enabled"):
            continue
        hours = int(rt.get("schedule_interval_hours", 168))
        if _last_run and datetime.utcnow() - _last_run < timedelta(hours=hours):
            continue
        scans = list_scans(limit=1)
        if not scans:
            continue
        profile = scans[0].profile
        if not (profile.username or profile.email or profile.full_name):
            continue
        logger.info("Scheduled scan starting for %s", profile.username or profile.full_name)
        try:
            await _engine.run_scan(profile, DEFAULT_MODULES)
            _last_run = datetime.utcnow()
            logger.info("Scheduled scan completed")
        except Exception as exc:
            logger.error("Scheduled scan failed: %s", exc)


def start_scheduler() -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_scheduler_loop())
    logger.info("Scan scheduler started")
