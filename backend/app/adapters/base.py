"""Provider adapter layer — wraps external OSINT tools without copying their code."""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import Finding, FindingCategory, IdentityProfile

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Abstract adapter for an external OSINT tool."""

    id: str = "base"
    name: str = "Base"
    license_name: str = "Unknown"
    category: str = "general"
    description: str = ""

    def __init__(self, tool_path: Path | None = None):
        self.tool_path = tool_path or self.default_path()

    @classmethod
    @abstractmethod
    def default_path(cls) -> Path: ...

    def is_available(self) -> bool:
        return self.tool_path.exists()

    @abstractmethod
    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        ...

    async def _run_subprocess(
        self, cmd: list[str], cwd: Path | None = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        timeout = timeout or settings.scan_timeout_seconds

        def _execute() -> tuple[int, str, str]:
            proc = subprocess.run(
                cmd,
                cwd=cwd or self.tool_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
            return proc.returncode, proc.stdout, proc.stderr

        return await asyncio.to_thread(_execute)

    def _make_finding(
        self,
        scan_id: str,
        platform: str,
        title: str,
        url: str,
        *,
        category: FindingCategory = FindingCategory.OTHER,
        description: str = "",
        snippet: str = "",
        confidence: float = 0.8,
        raw: dict[str, Any] | None = None,
    ) -> Finding:
        return Finding(
            scan_id=scan_id,
            source=self.id,
            provider=f"{self.name}Adapter",
            category=category,
            platform=platform,
            title=title,
            url=url,
            description=description,
            snippet=snippet,
            confidence=confidence,
            raw=raw or {},
        )


class MaigretAdapter(BaseAdapter):
    id = "maigret"
    name = "Maigret"
    license_name = "MIT"
    category = "username_discovery"
    description = "Username dossier across 3000+ sites"

    @classmethod
    def default_path(cls) -> Path:
        return settings.maigret_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not profile.username:
            return []
        scan_id = ""  # filled by engine
        maigret_bin = shutil.which("maigret")
        if not maigret_bin:
            return [
                self._make_finding(
                    scan_id,
                    "Maigret",
                    "Maigret not installed",
                    "",
                    category=FindingCategory.USERNAME,
                    description="Install with: pip install maigret",
                    confidence=0.0,
                )
            ]

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            cmd = [
                maigret_bin,
                profile.username,
                "--json",
                "simple",
                "--folderoutput",
                str(out_dir),
                "--timeout",
                "30",
            ]
            code, stdout, stderr = await self._run_subprocess(cmd, timeout=300)
            if code != 0:
                logger.warning("Maigret exit %s: %s", code, stderr[:500])
                return []

            findings: list[Finding] = []
            for json_file in out_dir.glob("*.json"):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        for site, info in data.items():
                            if isinstance(info, dict) and info.get("status") == "Claimed":
                                url = info.get("url_user", info.get("url", ""))
                                findings.append(
                                    self._make_finding(
                                        scan_id,
                                        site,
                                        f"Profile on {site}",
                                        url,
                                        category=FindingCategory.USERNAME,
                                        description=str(info.get("ids", "")),
                                        confidence=0.85,
                                        raw=info,
                                    )
                                )
                except (json.JSONDecodeError, OSError) as exc:
                    logger.debug("Maigret parse error: %s", exc)
            return findings


class SherlockAdapter(BaseAdapter):
    id = "sherlock"
    name = "Sherlock"
    license_name = "MIT"
    category = "username_discovery"
    description = "Username search across 400+ social networks"

    @classmethod
    def default_path(cls) -> Path:
        return settings.sherlock_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not profile.username:
            return []
        scan_id = ""
        sherlock_bin = shutil.which("sherlock")
        if not sherlock_bin:
            sherlock_py = self.tool_path / "sherlock_project" / "sherlock.py"
            if sherlock_py.exists():
                sherlock_bin = "python"
                cmd_prefix = ["python", str(sherlock_py)]
            else:
                return [
                    self._make_finding(
                        scan_id,
                        "Sherlock",
                        "Sherlock not installed",
                        "",
                        category=FindingCategory.USERNAME,
                        description="Install with: pipx install sherlock-project",
                        confidence=0.0,
                    )
                ]
        else:
            cmd_prefix = [sherlock_bin]

        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "results.json"
            cmd = cmd_prefix + [
                profile.username,
                "--json",
                str(json_path),
                "--print-found",
                "--no-color",
            ]
            code, _, stderr = await self._run_subprocess(cmd, timeout=300)
            if not json_path.exists():
                logger.warning("Sherlock no output: %s", stderr[:300])
                return []

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []

            findings: list[Finding] = []
            for site, info in data.items():
                if isinstance(info, dict) and info.get("status") == "Claimed":
                    url = info.get("url_user", "")
                    findings.append(
                        self._make_finding(
                            scan_id,
                            site,
                            f"Account on {site}",
                            url,
                            category=FindingCategory.USERNAME,
                            confidence=0.9,
                            raw=info,
                        )
                    )
            return findings


class BlackbirdAdapter(BaseAdapter):
    id = "blackbird"
    name = "Blackbird"
    license_name = "Educational/MIT-like"
    category = "username_discovery"
    description = "Username/email search with WhatsMyName integration"

    @classmethod
    def default_path(cls) -> Path:
        return settings.blackbird_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        scan_id = ""
        script = self.tool_path / "blackbird.py"
        if not script.exists():
            return []

        cmd = ["python", str(script)]
        if profile.username:
            cmd.extend(["--username", profile.username])
        elif profile.email:
            cmd.extend(["--email", profile.email])
        else:
            return []

        with tempfile.TemporaryDirectory() as tmp:
            json_out = Path(tmp) / "results.json"
            cmd.append("--json")
            code, stdout, stderr = await self._run_subprocess(
                cmd, cwd=self.tool_path, timeout=300
            )

            findings: list[Finding] = []
            # Try JSON output file in cwd or parse stdout
            for candidate in [json_out, self.tool_path / "results.json"]:
                if candidate.exists():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        items = data if isinstance(data, list) else data.get("results", [])
                        for item in items:
                            url = item.get("url", item.get("link", ""))
                            platform = item.get("site", item.get("platform", "Blackbird"))
                            findings.append(
                                self._make_finding(
                                    scan_id, platform, f"Profile on {platform}", url,
                                    category=FindingCategory.USERNAME,
                                    snippet=str(item),
                                    confidence=0.8,
                                    raw=item if isinstance(item, dict) else {},
                                )
                            )
                        if findings:
                            return findings
                    except (json.JSONDecodeError, OSError):
                        pass

            if code != 0:
                logger.warning("Blackbird exit %s: %s", code, stderr[:300])

            for line in (stdout + stderr).splitlines():
                if "http" in line.lower():
                    url = next((p for p in line.split() if p.startswith("http")), "")
                    if url:
                        findings.append(
                            self._make_finding(
                                scan_id, "Blackbird", "Discovered profile", url,
                                category=FindingCategory.USERNAME,
                                snippet=line.strip(), confidence=0.75,
                            )
                        )
            return findings


class HoleheAdapter(BaseAdapter):
    id = "holehe"
    name = "Holehe"
    license_name = "GPL-3.0"
    category = "email_exposure"
    description = "Email registration check on 120+ sites (subprocess isolation)"

    @classmethod
    def default_path(cls) -> Path:
        return settings.holehe_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not profile.email:
            return []
        scan_id = ""
        holehe_bin = shutil.which("holehe")
        if not holehe_bin:
            return [
                self._make_finding(
                    scan_id,
                    "Holehe",
                    "Holehe not installed",
                    "",
                    category=FindingCategory.EMAIL,
                    description="Install with: pip install holehe",
                    confidence=0.0,
                )
            ]

        cmd = [holehe_bin, profile.email, "--only-used"]
        code, stdout, stderr = await self._run_subprocess(cmd, timeout=300)
        output = stdout + stderr

        findings: list[Finding] = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("[") and "]" in line[:20]:
                continue
            lower = line.lower()
            if any(x in lower for x in ("[+]", "used", "exists", "yes")):
                parts = line.replace("[+]", "").replace("[✓]", "").strip().split()
                service = parts[0] if parts else "Unknown"
                if service.lower() in ("email", "checking", "target"):
                    continue
                findings.append(
                    self._make_finding(
                        scan_id, service, f"Email registered on {service}", "",
                        category=FindingCategory.EMAIL,
                        description=line, snippet=line, confidence=0.85,
                    )
                )
        return findings


class WhatsMyNameAdapter(BaseAdapter):
    """Live username checks against WMN detection database."""

    id = "whatsmyname"
    name = "WhatsMyName"
    license_name = "CC BY-SA 4.0"
    category = "username_discovery"
    description = "Live username check via WMN site database"

    @classmethod
    def default_path(cls) -> Path:
        return settings.whatsmyname_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not profile.username:
            return []
        from app.adapters.wmn_checker import check_username_wmn
        return await check_username_wmn(profile.username)


class SocialAnalyzerAdapter(BaseAdapter):
    id = "social_analyzer"
    name = "Social Analyzer"
    license_name = "AGPL-3.0"
    category = "social_discovery"
    description = "Multi-technique social profile discovery"

    @classmethod
    def default_path(cls) -> Path:
        return settings.social_analyzer_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not profile.username:
            return []
        app_py = self.tool_path / "app.py"
        if not app_py.exists():
            return []

        cmd = ["python", str(app_py), "--username", profile.username, "--mode", "fast"]
        code, stdout, _ = await self._run_subprocess(cmd, cwd=self.tool_path, timeout=600)
        findings: list[Finding] = []
        for line in stdout.splitlines():
            if "http" in line:
                url = next((w for w in line.split() if w.startswith("http")), "")
                if url:
                    findings.append(
                        self._make_finding(
                            "",
                            "Social Analyzer",
                            "Social profile candidate",
                            url,
                            category=FindingCategory.SOCIAL,
                            snippet=line.strip(),
                            confidence=0.7,
                        )
                    )
        return findings


class SpiderFootAdapter(BaseAdapter):
    id = "spiderfoot"
    name = "SpiderFoot"
    license_name = "MIT"
    category = "advanced_intelligence"
    description = "Passive OSINT automation (opt-in, module allowlist)"

    @classmethod
    def default_path(cls) -> Path:
        return settings.spiderfoot_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not settings.enable_spiderfoot:
            return []
        sf_py = self.tool_path / "sf.py"
        sfcli = self.tool_path / "sfcli.py"
        if not sf_py.exists():
            return []

        target = profile.email or profile.username or profile.full_name
        if not target:
            return []

        # Passive modules only
        passive = "sfp_accounts,sfp_email,sfp_wikipedia,sfp_googlesearch"
        cli = sfcli if sfcli.exists() else sf_py
        cmd = [
            "python", str(cli),
            "-s", target,
            "-m", passive,
            "-q",
        ]
        code, stdout, stderr = await self._run_subprocess(cmd, cwd=self.tool_path, timeout=600)
        findings: list[Finding] = []
        for line in (stdout + stderr).splitlines():
            if "http" in line.lower() or "ACCOUNT" in line or "EMAIL" in line:
                url = next((w for w in line.split() if w.startswith("http")), "")
                findings.append(
                    self._make_finding(
                        "", "SpiderFoot", line.strip()[:80], url,
                        category=FindingCategory.ADVANCED,
                        snippet=line.strip(), confidence=0.7,
                    )
                )
        return findings[:50]


class ReconNgAdapter(BaseAdapter):
    id = "reconng"
    name = "Recon-ng"
    license_name = "GPL-style"
    category = "advanced_intelligence"
    description = "Passive recon framework (Phase 4)"

    @classmethod
    def default_path(cls) -> Path:
        return settings.reconng_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not settings.enable_reconng:
            return []
        recon = self.tool_path / "recon-ng"
        if not recon.exists() and not (self.tool_path / "recon").exists():
            return []

        findings: list[Finding] = []
        target = profile.email or profile.username or profile.full_name
        if not target:
            return []

        # Passive recon-ng modules via scripted input
        modules = ["recon/domains-contacts/whois_pocs", "recon/profiles-profiles/namechk"]
        for mod in modules:
            cmd = ["python", str(self.tool_path / "recon-ng"), "--module", mod]
            try:
                code, stdout, stderr = await self._run_subprocess(cmd, timeout=120)
                for line in (stdout + stderr).splitlines():
                    if "http" in line or "@" in line:
                        findings.append(
                            self._make_finding(
                                "", "Recon-ng", line.strip()[:80], "",
                                category=FindingCategory.ADVANCED,
                                snippet=line.strip(), confidence=0.6,
                            )
                        )
            except Exception:
                pass
        return findings[:30]


class GHuntAdapter(BaseAdapter):
    id = "ghunt"
    name = "GHunt"
    license_name = "AGPL-3.0"
    category = "advanced_intelligence"
    description = "Google account OSINT (opt-in, requires login)"

    @classmethod
    def default_path(cls) -> Path:
        return settings.ghunt_path

    async def scan(self, profile: IdentityProfile) -> list[Finding]:
        if not settings.enable_ghunt or not profile.email:
            return []
        ghunt_bin = shutil.which("ghunt")
        if not ghunt_bin:
            return [
                self._make_finding(
                    "", "GHunt", "GHunt not installed — pipx install ghunt", "",
                    category=FindingCategory.ADVANCED, confidence=0.0,
                    description="Install GHunt and run ghunt login first",
                )
            ]

        with tempfile.TemporaryDirectory() as tmp:
            out_json = Path(tmp) / "ghunt.json"
            cmd = [ghunt_bin, "email", profile.email, "--json", str(out_json)]
            code, stdout, stderr = await self._run_subprocess(cmd, timeout=120)
            findings: list[Finding] = []

            if out_json.exists():
                try:
                    data = json.loads(out_json.read_text(encoding="utf-8"))
                    findings.append(
                        self._make_finding(
                            "", "GHunt", f"Google data for {profile.email}", "",
                            category=FindingCategory.ADVANCED,
                            description=json.dumps(data)[:500],
                            snippet=str(data.get("name", "")),
                            confidence=0.9 if data else 0.3,
                            raw=data if isinstance(data, dict) else {},
                        )
                    )
                    return findings
                except (json.JSONDecodeError, OSError):
                    pass

            if "login" in (stdout + stderr).lower():
                return [
                    self._make_finding(
                        "", "GHunt", "Authentication required", "",
                        category=FindingCategory.ADVANCED,
                        description="Run: ghunt login",
                        confidence=0.0,
                    )
                ]
        return []


ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "maigret": MaigretAdapter,
    "sherlock": SherlockAdapter,
    "blackbird": BlackbirdAdapter,
    "holehe": HoleheAdapter,
    "whatsmyname": WhatsMyNameAdapter,
    "social_analyzer": SocialAnalyzerAdapter,
    "spiderfoot": SpiderFootAdapter,
    "reconng": ReconNgAdapter,
    "ghunt": GHuntAdapter,
}


def get_adapter(provider_id: str) -> BaseAdapter:
    cls = ADAPTER_REGISTRY.get(provider_id)
    if not cls:
        raise ValueError(f"Unknown provider: {provider_id}")
    return cls()


def list_providers() -> list[dict]:
    result = []
    for pid, cls in ADAPTER_REGISTRY.items():
        adapter = cls()
        result.append(
            {
                "id": pid,
                "name": adapter.name,
                "available": adapter.is_available(),
                "path": str(adapter.tool_path),
                "license": adapter.license_name,
                "category": adapter.category,
                "description": adapter.description,
                "enabled": True,
            }
        )
    return result
