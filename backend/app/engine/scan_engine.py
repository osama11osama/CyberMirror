"""CyberMirror native scan orchestration — async background support."""

import logging
from datetime import datetime

from app.engine.job_store import complete_job, create_job, fail_job, update_job
from app.models.schemas import Finding, IdentityProfile, ScanDetail, ScanStartResponse
from app.modules.registry import DEFAULT_MODULES, get_module
from app.services.risk_engine import analyze_finding, compute_risk_score
from app.storage.database import (
    create_scan,
    get_scan,
    row_to_finding,
    save_findings,
    update_scan_status,
)

logger = logging.getLogger(__name__)


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.url.lower().strip(), f.platform.lower())
        if not f.url:
            unique.append(f)
            continue
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


class ScanEngine:
    def start_scan(self, profile: IdentityProfile, modules: list[str] | None = None) -> ScanStartResponse:
        """Create scan record and return immediately — call run_scan_background separately."""
        modules = modules or DEFAULT_MODULES
        scan_id = create_scan(profile, modules)
        create_job(scan_id, modules)
        return ScanStartResponse(
            id=scan_id,
            status="running",
            message="Scan queued",
            providers=modules,
        )

    async def run_scan_background(
        self, scan_id: str, profile: IdentityProfile, modules: list[str]
    ) -> None:
        try:
            all_findings = await self._execute_modules(scan_id, profile, modules)
            all_findings = dedupe_findings(all_findings)

            for finding in all_findings:
                finding.scan_id = scan_id
                analyze_finding(finding, profile)

            save_findings(all_findings)
            risk_score = compute_risk_score(all_findings)
            update_scan_status(scan_id, "completed", len(all_findings), risk_score)
            complete_job(scan_id, len(all_findings))
            logger.info("Scan %s completed — %d findings", scan_id[:8], len(all_findings))
        except Exception as exc:
            logger.exception("Scan %s failed", scan_id[:8])
            fail_job(scan_id, str(exc))
            update_scan_status(scan_id, "failed", 0, 0)

    async def run_scan(
        self, profile: IdentityProfile, modules: list[str] | None = None
    ) -> ScanDetail:
        """Blocking scan — waits for completion (legacy / scheduler)."""
        modules = modules or DEFAULT_MODULES
        started = self.start_scan(profile, modules)
        await self.run_scan_background(started.id, profile, modules)
        data = get_scan(started.id)
        if not data:
            raise RuntimeError("Scan record missing after run")
        row = data["scan"]
        findings = [row_to_finding(f) for f in data["findings"]]
        return ScanDetail(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            profile=profile,
            status=row["status"],
            providers=modules,
            finding_count=row["finding_count"],
            risk_score=row["risk_score"],
            findings=findings,
        )

    async def _execute_modules(
        self, scan_id: str, profile: IdentityProfile, modules: list[str]
    ) -> list[Finding]:
        all_findings: list[Finding] = []
        total = len(modules)

        for i, module_id in enumerate(modules):
            pct = int(((i + 1) / total) * 100) if total else 100
            mod = get_module(module_id)
            update_job(
                scan_id,
                progress=pct,
                current_provider=module_id,
                message=f"Running {mod.name} ({i + 1}/{total})…",
            )
            try:
                batch = await mod.scan(profile, scan_id)
                all_findings.extend(batch)
                update_job(scan_id, findings_so_far=len(all_findings))
                logger.info("Module %s: %d findings", module_id, len(batch))
            except Exception as exc:
                logger.error("Module %s failed: %s", module_id, exc)

        return all_findings
