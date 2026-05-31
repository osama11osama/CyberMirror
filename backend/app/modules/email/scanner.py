"""Native email exposure scanner — checks public registration signals."""

import logging

import httpx

from app.models.schemas import Finding, FindingCategory, IdentityProfile
from app.modules.base import NativeModule
from app.modules.identity.web_search import WebSearchModule

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

        # Web search for email in public results
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

        # Gravatar public profile check (email hash not needed — username-style)
        local = email.split("@")[0]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://en.gravatar.com/{local}")
                if resp.status_code == 200 and "404" not in resp.text[:2000].lower():
                    findings.append(Finding(
                        scan_id=scan_id,
                        source=self.id,
                        provider="EmailScanModule",
                        category=FindingCategory.EMAIL,
                        platform="Gravatar",
                        title="Possible Gravatar profile linked to email prefix",
                        url=f"https://en.gravatar.com/{local}",
                        confidence=0.6,
                        description="Public avatar/profile may reveal identity",
                    ))
        except Exception as exc:
            logger.debug("Gravatar check failed: %s", exc)

        # Registration signal probes (public endpoints — no password sent)
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            for probe in _registration_probes(email):
                try:
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


def _registration_probes(email: str) -> list[dict]:
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
            "url": f"https://api.twitter.com/i/users/email_available.json?email={email}",
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
    ]


async def _run_probe(client: httpx.AsyncClient, probe: dict) -> str | None:
    kwargs: dict = {}
    if probe.get("json"):
        kwargs["json"] = probe["json"]
    resp = await client.request(probe["method"], probe["url"], **kwargs)
    body = resp.text.lower()
    marker = probe["exists_text"].lower()
    if marker in body:
        return f"Registration signal detected via {probe['platform']} API"
    return None
