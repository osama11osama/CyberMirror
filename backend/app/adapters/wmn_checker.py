"""WhatsMyName live username checker using wmn-data.json."""

import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings
from app.models.schemas import Finding, FindingCategory, IdentityProfile

logger = logging.getLogger(__name__)

MAX_SITES = 40
CONCURRENCY = 8
TIMEOUT = 12


async def check_username_wmn(
    username: str, scan_id: str = "", limit: int = MAX_SITES
) -> list[Finding]:
    data_file = settings.whatsmyname_path / "wmn-data.json"
    if not data_file.exists():
        return []

    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    sites = [s for s in data.get("sites", []) if not s.get("disabled")][:limit]
    findings: list[Finding] = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async def check_site(site: dict, client: httpx.AsyncClient) -> Finding | None:
        async with sem:
            name = site.get("name", "Unknown")
            uri = site.get("uri_check", "").replace("{account}", quote(username))
            if not uri.startswith("http"):
                return None
            try:
                resp = await client.get(uri, follow_redirects=True)
                text = resp.text
                estring = site.get("e_string", "")
                mstring = site.get("m_string", "")
                if estring and estring in text:
                    if mstring and mstring in text:
                        return None
                    url = site.get("uri_pretty", uri).replace("{account}", username)
                    return Finding(
                        scan_id=scan_id,
                        source="whatsmyname",
                        provider="WhatsMyNameAdapter",
                        category=FindingCategory.USERNAME,
                        platform=name,
                        title=f"Profile found on {name}",
                        url=url,
                        description=f"WMN detection match for {username}",
                        confidence=0.88,
                        raw={"site": name, "uri": uri},
                    )
            except Exception as exc:
                logger.debug("WMN check failed %s: %s", name, exc)
            return None

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": "CyberMirror-SelfAudit/0.2"},
    ) as client:
        tasks = [check_site(s, client) for s in sites]
        results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            findings.append(r)
    return findings
