"""CyberMirror native scan orchestration — parallel modules, live findings, cancel."""

import asyncio
import logging
from datetime import datetime

from app.engine.job_store import (
    add_module_error,
    append_live_findings,
    complete_job,
    create_job,
    fail_job,
    get_job,
    is_cancelled,
    update_job,
)
from app.engine.scan_context import ScanCancelled
from app.models.schemas import Finding, IdentityProfile, ScanDetail, ScanStartResponse
from app.modules.identity.correlator import correlate_findings
from app.modules.registry import DEFAULT_MODULES, get_module
from app.services.risk_engine import analyze_finding, compute_risk_score
from app.services.investigation_budget import clear_budget, default_budget, get_budget
from app.services.runtime_settings import get_enabled_modules
from app.storage.database import (
    create_scan,
    delete_findings_for_scan,
    get_scan,
    row_to_finding,
    save_findings,
    update_scan_status,
)

logger = logging.getLogger(__name__)

CORRELATOR_ID = "identity_correlator"


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


def _resolve_modules(modules: list[str] | None) -> list[str]:
    enabled = set(get_enabled_modules())
    chosen = modules or get_enabled_modules() or DEFAULT_MODULES
    return [m for m in chosen if m in enabled]


class ScanEngine:
    def start_scan(self, profile: IdentityProfile, modules: list[str] | None = None) -> ScanStartResponse:
        modules = _resolve_modules(modules)
        scan_id = create_scan(profile, modules)
        create_job(scan_id, modules)
        default_budget(scan_id)
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
            if is_cancelled(scan_id):
                update_scan_status(scan_id, "cancelled", len(all_findings), 0)
                return

            all_findings = dedupe_findings(all_findings)
            for finding in all_findings:
                finding.scan_id = scan_id
                analyze_finding(finding, profile)

            delete_findings_for_scan(scan_id)
            save_findings(all_findings)
            risk_score = compute_risk_score(all_findings)
            update_scan_status(scan_id, "completed", len(all_findings), risk_score)
            complete_job(scan_id, len(all_findings))
            logger.info("Scan %s completed — %d findings", scan_id[:8], len(all_findings))
        except Exception as exc:
            logger.exception("Scan %s failed", scan_id[:8])
            fail_job(scan_id, str(exc))
            update_scan_status(scan_id, "failed", 0, 0)
        finally:
            budget = get_budget(scan_id)
            if budget is not None:
                update_job(scan_id, investigation_budget=budget.as_dict())
            clear_budget(scan_id)

    async def run_scan(
        self, profile: IdentityProfile, modules: list[str] | None = None
    ) -> ScanDetail:
        modules = _resolve_modules(modules)
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
        parallel_ids = [m for m in modules if m != CORRELATOR_ID]
        run_correlator = CORRELATOR_ID in modules
        total = len(parallel_ids) + (1 if run_correlator else 0)
        completed = 0

        async def run_one(module_id: str) -> list[Finding]:
            nonlocal completed
            if is_cancelled(scan_id):
                return []
            mod = get_module(module_id)
            update_job(
                scan_id,
                current_provider=module_id,
                message=f"Running {mod.name}…",
            )
            try:
                batch = await mod.scan(profile, scan_id)
                for f in batch:
                    f.scan_id = scan_id
                    analyze_finding(f, profile)
                append_live_findings(scan_id, batch)
                completed += 1
                prev = get_job(scan_id) or {}
                new_count = prev.get("findings_so_far", 0) + len(batch)
                pct = int((completed / total) * 100) if total else 100
                update_job(
                    scan_id,
                    progress=pct,
                    modules_completed=completed,
                    findings_so_far=new_count,
                )
                logger.info("Module %s: %d findings", module_id, len(batch))
                return batch
            except ScanCancelled:
                logger.info("Module %s cancelled", module_id)
                return []
            except Exception as exc:
                logger.error("Module %s failed: %s", module_id, exc)
                add_module_error(scan_id, module_id, str(exc))
                completed += 1
                return []

        tasks = {mid: asyncio.create_task(run_one(mid)) for mid in parallel_ids}
        pending = set(tasks.values())
        all_findings: list[Finding] = []

        while pending:
            if is_cancelled(scan_id):
                for task in pending:
                    task.cancel()
                break
            done, pending = await asyncio.wait(
                pending,
                timeout=0.5,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                try:
                    batch = task.result()
                    if batch:
                        all_findings.extend(batch)
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.error("Module task error: %s", exc)

        if is_cancelled(scan_id):
            return all_findings

        if run_correlator and not is_cancelled(scan_id):
            update_job(scan_id, current_provider=CORRELATOR_ID, message="Correlating findings…")
            corr = correlate_findings(profile, all_findings, scan_id)
            for f in corr:
                analyze_finding(f, profile)
            append_live_findings(scan_id, corr)
            all_findings.extend(corr)
            update_job(scan_id, progress=100, findings_so_far=len(all_findings))

        return all_findings

    def cancel_scan(self, scan_id: str) -> bool:
        from app.engine.job_store import cancel_job
        data = get_scan(scan_id)
        if not data or data["scan"]["status"] not in ("running",):
            job = get_job(scan_id)
            if not job or job.get("status") != "running":
                return False
        budget = get_budget(scan_id)
        if budget is not None:
            budget.cancel()
        return cancel_job(scan_id)
