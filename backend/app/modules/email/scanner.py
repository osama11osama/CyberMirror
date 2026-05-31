"""Native email exposure scanner — checks public registration signals."""

import hashlib
import logging
from urllib.parse import quote

import httpx

from app.engine.scan_context import raise_if_cancelled
from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.modules.identity.web_search import WebSearchModule
from app.services.rate_limiter import throttle

logger = logging.getLogger(__name__)


class EmailScanModule(NativeModule):
    id = "email_scan"
    name = "CyberMirror Email Scanner"
    description = "Detects public email exposure via web search and registration signals"
    category = "email_exposure"

    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        email = profile.email.strip()
        if not email or "@" not in email:
            return []

        findings: list[Finding] = []

        search = WebSearchModule(max_queries=3, results_per_query=5)
        mini = IdentityProfile(email=email, full_name=profile.full_name, phone=profile.phone)
        for hit in await search.scan(mini, scan_id):
            combined = f"{hit.title} {hit.snippet} {hit.url}".lower()
            if email.lower() in combined:
                findings.append(Finding(
                    scan_id=scan_id,
                    source=self.id,
                    provider="EmailScanModule",
                    category=FindingCategory.EMAIL,
                    platform="Web",
                    title="Email exposed in public web result",
                    url=hit.url,
                    snippet=hit.snippet,
                    description=f"Found via query: {hit.description}",
                    confidence=0.88,
                ))

        raise_if_cancelled(scan_id)
        gravatar = await _check_gravatar(email, scan_id)
        if gravatar:
            findings.append(gravatar)

        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            for probe in _registration_probes(email):
                raise_if_cancelled(scan_id)
                try:
                    await throttle(0.6)
                    hit = await _run_probe(client, probe)
                    if hit:
                        findings.append(Finding(
                            scan_id=scan_id,
                            source=self.id,
                            provider="EmailScanModule",
                            category=FindingCategory.EMAIL,
                            platform=probe["platform"],
                            title=f"Email registered on {probe['platform']}",
                            url=probe.get("profile_url", ""),
                            confidence=probe.get("confidence", 0.75),
                            description=hit,
                        ))
                except Exception as exc:
                    logger.debug("%s probe failed: %s", probe["platform"], exc)

        return findings


async def _check_gravatar(email: str, scan_id: str) -> Finding | None:
    digest = hashlib.md5(email.lower().strip().encode()).hexdigest()
    url = f"https://www.gravatar.com/avatar/{digest}?d=404"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.head(url)
        if resp.status_code == 200:
            return Finding(
                scan_id=scan_id,
                source="email_scan",
                provider="EmailScanModule",
                category=FindingCategory.EMAIL,
                platform="Gravatar",
                title="Gravatar profile exists for this email",
                url=f"https://gravatar.com/{digest}",
                confidence=0.82,
                description="Public avatar may reveal identity or link accounts",
            )
    except Exception as exc:
        logger.debug("Gravatar check failed: %s", exc)
    return None


def _registration_probes(email: str) -> list[dict]:
    enc = quote(email)
    return [
        {
            "platform": "Spotify",
            "method": "POST",
            "url": "https://spclient.wg.spotify.com/signup/public/v1/account",
            "json": {
                "account_details": {"birthdate": "1990-01-01", "consent_flags": [], "displayname": "x", "gender": 1},
                "callback_uri": "https://www.spotify.com/signup/challenge",
                "client_info": {"api_key": "142b583129b2df879de137466939aaa367167c1a", "platform": "www"},
                "email": email,
                "password": "NotARealPassword123!",
            },
            "exists_text": "email is already registered",
            "profile_url": "https://open.spotify.com/",
            "confidence": 0.85,
        },
        {
            "platform": "Twitter/X",
            "method": "GET",
            "url": f"https://api.twitter.com/i/users/email_available.json?email={enc}",
            "exists_text": '"taken":true',
            "profile_url": "https://twitter.com/",
            "confidence": 0.8,
        },
        {
            "platform": "Adobe",
            "method": "POST",
            "url": "https://auth.services.adobe.com/signin/v2/users/accounts",
            "json": {"username": email, "usernameType": "EMAIL"},
            "exists_text": "account_exists",
            "profile_url": "https://account.adobe.com/",
            "confidence": 0.78,
        },
        {
            "platform": "Microsoft",
            "method": "GET",
            "url": f"https://login.microsoftonline.com/common/GetCredentialType?username={enc}",
            "exists_text": '"ifexistsresult":0',
            "profile_url": "https://account.microsoft.com/",
            "confidence": 0.8,
        },
        {
            "platform": "GitHub",
            "method": "POST",
            "url": "https://github.com/signup/check/email",
            "json": {"value": email},
            "exists_text": "already associated",
            "profile_url": "https://github.com/",
            "confidence": 0.82,
        },
        {
            "platform": "Amazon",
            "method": "POST",
            "url": "https://www.amazon.com/ap/register",
            "data": {"email": email, "create": "0"},
            "exists_text": "already an account",
            "profile_url": "https://www.amazon.com/",
            "confidence": 0.7,
        },
        {
            "platform": "Pinterest",
            "method": "GET",
            "url": f"https://www.pinterest.com/resource/EmailExistsResource/get/?source_url=%2F&data=%7B%22options%22%3A%7B%22email%22%3A%22{enc}%22%7D%7D",
            "exists_text": '"status":"yes"',
            "profile_url": "https://www.pinterest.com/",
            "confidence": 0.75,
        },
        {
            "platform": "Discord",
            "method": "POST",
            "url": "https://discord.com/api/v9/auth/register",
            "json": {"email": email, "username": "x", "password": "Xx123456789!", "consent": True},
            "exists_text": "email is already registered",
            "profile_url": "https://discord.com/",
            "confidence": 0.72,
        },
    ]


async def _run_probe(client: httpx.AsyncClient, probe: dict) -> str | None:
    kwargs: dict = {}
    if probe.get("json"):
        kwargs["json"] = probe["json"]
    if probe.get("data"):
        kwargs["data"] = probe["data"]
    resp = await client.request(probe["method"], probe["url"], **kwargs)
    body = resp.text.lower()
    marker = probe["exists_text"].lower()
    if marker in body:
        return f"Registration signal detected via {probe['platform']} API"
    return None
