"""FastAPI route handlers."""



import json

from contextlib import asynccontextmanager

from datetime import datetime
from app.services.timeutil import parse_iso_datetime



from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.engine.job_store import get_job, get_live_findings

from app.engine.scan_engine import ScanEngine

from app.models.schemas import (

    DashboardStats,

    ExportRequest,

    IdentityProfile,

    ScanCompareResult,

    ScanDetail,

    ScanRequest,

    ScanStartResponse,

    ScanSummary,

    SettingsUpdate,

)

from app.modules.registry import DEFAULT_MODULES, list_modules

from app.services.logging_setup import setup_logging

from app.services.report_exporter import export_csv, export_html, export_json, export_pdf

from app.services.cache import clear_cache

from app.services.crypto import EncryptionError

from app.services.runtime_settings import apply_runtime, get_enabled_modules, load_runtime, save_runtime

from app.services.scheduler import start_scheduler

from app.services.secrets import get_secret

from app.storage.database import (
    compare_scans,
    count_scans,
    delete_scan,
    get_scan,
    init_db,
    list_scans,
    load_intelligence,
    profile_from_row,
    redact_intelligence_artifacts,
    risk_trends,
    row_to_finding,
    save_intelligence,
    sync_risk_score,
)
from app.modules.username.wmn_loader import wmn_status



router = APIRouter(prefix="/api")

engine = ScanEngine()





@asynccontextmanager

async def lifespan(app):

    setup_logging()

    apply_runtime()

    from app.storage.database import mark_orphaned_running_scans

    orphaned = mark_orphaned_running_scans()
    if orphaned:
        import logging

        logging.getLogger("cybermirror").info(
            "Marked %s orphaned running scan(s) as failed after restart", orphaned
        )

    start_scheduler()

    if settings.api_auth_enabled:
        from app.services.auth import get_or_create_token
        import logging

        get_or_create_token()  # ensure data/.api_token exists for operators
        logging.getLogger("cybermirror").info(
            "API auth is enabled. Unlock the UI with #api_token=<token> or the in-app unlock form. "
            "Read the token from data/.api_token (Docker: docker compose exec cybermirror cat /app/data/.api_token). "
            "HTTP endpoints never return the API token."
        )

    yield





@router.get("/health")

def health():

    rt = load_runtime()

    return {

        "status": "ok",

        "app": settings.app_name,

        "version": settings.app_version,

        "release_name": settings.app_release_name,

        "engine": "CyberMirror Native",

        "slogan": "See Yourself as the Internet Sees You",

        "modules": len(DEFAULT_MODULES),

        "username_scan_limit": rt.get("username_scan_limit"),

        "wmn": wmn_status(),

        "api_auth_enabled": settings.api_auth_enabled,

        "encryption_enabled": settings.encryption_enabled,

    }





@router.get("/modules")

def modules():

    return list_modules()





@router.get("/providers")

def providers_legacy():

    return list_modules()





@router.get("/settings")

def get_settings():

    rt = load_runtime()

    return {

        "engine": "native",

        "default_modules": DEFAULT_MODULES,

        "enabled_modules": get_enabled_modules(),

        "hibp_api_key_set": bool(get_secret("hibp_api_key") or settings.hibp_api_key),

        **{k: v for k, v in rt.items() if k != "hibp_api_key"},

    }





@router.put("/settings")

def update_settings(body: SettingsUpdate):

    data = {}

    if body.serpapi_key is not None:

        settings.serpapi_key = body.serpapi_key or None

    for field in (

        "hibp_api_key", "username_scan_limit", "web_search_max_queries",

        "web_search_results_per_query", "wmn_data_path", "playwright_enabled",

        "schedule_enabled", "schedule_interval_hours", "cache_ttl_seconds",

        "ahmia_max_results", "ahmia_max_queries",

        "enabled_modules", "locale",

    ):

        val = getattr(body, field, None)

        if val is not None:

            data[field] = val

    if data:

        try:

            save_runtime(data)

        except EncryptionError:

            raise HTTPException(

                500,

                "Could not encrypt sensitive settings. Check local encryption configuration.",

            )

    return get_settings()





@router.post("/cache/clear")

def cache_clear():

    deleted = clear_cache()

    return {"cleared": deleted}





@router.get("/dashboard/trends")

def dashboard_trends(limit: int = Query(20, ge=2, le=100)):

    return {"scans": risk_trends(limit)}





@router.post("/scans")

async def start_scan(body: ScanRequest, background_tasks: BackgroundTasks):

    modules = body.providers or get_enabled_modules()

    try:

        if body.async_mode:

            started = engine.start_scan(body.profile, modules)

            background_tasks.add_task(

                engine.run_scan_background, started.id, body.profile, modules

            )

            return started

        return await engine.run_scan(body.profile, modules)

    except EncryptionError:

        raise HTTPException(

            500,

            "Could not encrypt the scan profile. Check local encryption configuration.",

        )





@router.get("/scans", response_model=list[ScanSummary])

def scans_list(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):

    return list_scans(limit=limit, offset=offset)





@router.get("/scans/count")

def scans_count():

    return {"total": count_scans()}





@router.delete("/scans/{scan_id}")

def scan_delete(scan_id: str):

    if not delete_scan(scan_id):

        raise HTTPException(404, "Scan not found")

    return {"deleted": True, "scan_id": scan_id}





@router.post("/scans/{scan_id}/cancel")

def scan_cancel(scan_id: str):

    if not engine.cancel_scan(scan_id):

        raise HTTPException(404, "Scan not running or not found")

    return {"cancelled": True, "scan_id": scan_id}





@router.get("/scans/{scan_id}/findings/live")

def scan_live_findings(scan_id: str):

    live = get_live_findings(scan_id)

    if live:

        return {"findings": live, "count": len(live)}

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    return {"findings": [row_to_finding(f).model_dump() for f in data["findings"]], "count": len(data["findings"])}





@router.get("/scans/{scan_id}", response_model=ScanDetail)

def scan_detail(scan_id: str):

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    row = data["scan"]

    findings = [row_to_finding(f) for f in data["findings"]]

    from app.services.exposure_scoring import compute_exposure_score

    explanation = compute_exposure_score(findings).as_dict()
    score = sync_risk_score(row["id"], findings, stored=row["risk_score"])
    explanation["score"] = score

    # Detail view always uses the live evidence-aware score so the number and
    # explanation stay consistent (legacy arithmetic-mean rows are recomputed here).
    return ScanDetail(

        id=row["id"],

        created_at=parse_iso_datetime(row["created_at"]),

        profile=profile_from_row(row),

        status=row["status"],

        providers=json.loads(row["providers"]),

        finding_count=row["finding_count"],

        risk_score=score,

        findings=findings,

        risk_explanation=explanation,

    )





@router.get("/scans/{scan_id}/status")

def scan_status(scan_id: str):

    job = get_job(scan_id)

    if job:

        return job

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    return {

        "scan_id": scan_id,

        "status": data["scan"]["status"],

        "progress": 100 if data["scan"]["status"] == "completed" else 0,

        "message": data["scan"]["status"],

        "findings_so_far": data["scan"]["finding_count"],

    }





@router.get("/scans/compare/{scan_a}/{scan_b}", response_model=ScanCompareResult)

def scan_compare(scan_a: str, scan_b: str):

    result = compare_scans(scan_a, scan_b)

    if result is None:

        raise HTTPException(404, "One or both scans not found")

    return result





@router.get("/scans/{scan_id}/graph")

def scan_graph(scan_id: str):

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    profile = profile_from_row(data["scan"])

    findings = [row_to_finding(f) for f in data["findings"]]

    intel = load_intelligence(scan_id)

    from app.services.graph_builder import build_graph, enrich_graph_with_intelligence

    graph = build_graph(profile, findings)

    if intel:

        graph = enrich_graph_with_intelligence(graph, intel)

    return graph





@router.get("/scans/{scan_id}/intelligence")

def scan_intelligence(scan_id: str, refresh: bool = Query(False)):

    return _intelligence_for_scan(scan_id, refresh=bool(refresh))





def _intelligence_for_scan(scan_id: str, *, refresh: bool = False) -> dict:

    """Load cached intelligence or build it. ``refresh`` must be a plain bool."""

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    if not refresh:

        existing = load_intelligence(scan_id)

        if existing:

            return existing

    profile = profile_from_row(data["scan"])

    findings = [row_to_finding(f) for f in data["findings"]]

    from app.services.intelligence_pipeline import analyze_finding_pages
    from app.services.investigation_budget import claim_budget, clear_budget

    budget = claim_budget(scan_id)
    if budget is None:
        raise HTTPException(409, "Investigation already active for this scan")

    try:
        payload = analyze_finding_pages(
            profile,
            findings,
            scan_id=scan_id,
            budget=budget,
        )
        save_intelligence(scan_id, payload)
        return payload
    finally:
        clear_budget(scan_id, expected=budget)





@router.get("/scans/{scan_id}/timeline")
def scan_timeline(
    scan_id: str,
    event_type: str | None = None,
    platform: str | None = None,
    location: str | None = None,
    min_confidence: float | None = None,
    verification: str | None = None,
    origin: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    from datetime import date as date_cls

    from app.services.timeline_builder import TimelineEntry, filter_timeline_entries

    intel = _intelligence_for_scan(scan_id, refresh=False)
    timeline = intel.get("timeline") or {"dated": [], "unknown_date": []}
    dated = [TimelineEntry.model_validate(e) for e in timeline.get("dated") or []]
    unknown = [TimelineEntry.model_validate(e) for e in timeline.get("unknown_date") or []]

    def _parse(value: str | None):
        if not value:
            return None
        try:
            return date_cls.fromisoformat(value[:10])
        except ValueError:
            return None

    if any(
        [
            event_type,
            platform,
            location,
            min_confidence is not None,
            verification,
            origin,
            date_from,
            date_to,
        ]
    ):
        dated, unknown = filter_timeline_entries(
            dated,
            unknown,
            event_type=event_type,
            platform=platform,
            location=location,
            min_confidence=min_confidence,
            verification=verification,
            origin=origin,
            date_from=_parse(date_from),
            date_to=_parse(date_to),
        )
    return {
        "dated": [e.model_dump(mode="json") for e in dated],
        "unknown_date": [e.model_dump(mode="json") for e in unknown],
    }





@router.get("/scans/{scan_id}/journal")

def scan_journal(scan_id: str):

    intel = _intelligence_for_scan(scan_id, refresh=False)

    return intel.get("journal") or {"scan_id": scan_id, "steps": []}





@router.get("/investigation/budget/defaults")

def budget_defaults():

    from app.services.investigation_budget import FORBIDDEN_CAPABILITIES, default_budget

    return default_budget("preview").as_dict() | {

        "forbidden_capabilities": list(FORBIDDEN_CAPABILITIES),

    }





@router.get("/scans/{scan_id}/artifacts")

def list_scan_artifacts(scan_id: str):

    if not get_scan(scan_id):

        raise HTTPException(404, "Scan not found")

    from app.services.investigation_budget import list_deep_artifacts, validate_artifact_scan_id

    try:

        validate_artifact_scan_id(scan_id)

    except ValueError as exc:

        raise HTTPException(400, str(exc)) from exc

    return {"scan_id": scan_id, "files": list_deep_artifacts(scan_id)}





@router.delete("/scans/{scan_id}/artifacts")

def delete_scan_artifacts(scan_id: str):

    if not get_scan(scan_id):

        raise HTTPException(404, "Scan not found")

    from app.services.investigation_budget import delete_deep_artifacts, validate_artifact_scan_id

    try:

        validate_artifact_scan_id(scan_id)

    except ValueError as exc:

        raise HTTPException(400, str(exc)) from exc

    deleted_files = delete_deep_artifacts(scan_id)

    redacted = redact_intelligence_artifacts(scan_id)

    return {"deleted": deleted_files, "redacted_payload_artifacts": redacted}





@router.get("/scans/{scan_id}/dashboard", response_model=DashboardStats)

def scan_dashboard(scan_id: str):

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    findings = [row_to_finding(f) for f in data["findings"]]

    by_source: dict[str, int] = {}

    by_category: dict[str, int] = {}

    by_risk: dict[str, int] = {}

    high = 0

    for f in findings:

        by_source[f.source] = by_source.get(f.source, 0) + 1

        by_category[f.category.value] = by_category.get(f.category.value, 0) + 1

        by_risk[f.risk_level.value] = by_risk.get(f.risk_level.value, 0) + 1

        if f.risk_level.value in ("Critical", "High"):

            high += 1

    row = data["scan"]

    score = sync_risk_score(row["id"], findings, stored=row["risk_score"])

    return DashboardStats(

        total_findings=len(findings),

        risk_score=score,

        by_source=by_source,

        by_category=by_category,

        by_risk=by_risk,

        high_risk_count=high,

        recent_scans=list_scans(5),

    )





@router.post("/scans/{scan_id}/export")

def export_scan(scan_id: str, body: ExportRequest):

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    row = data["scan"]

    findings = [row_to_finding(f) for f in data["findings"]]

    score = sync_risk_score(row["id"], findings, stored=row["risk_score"])

    summary = ScanSummary(

        id=row["id"],

        created_at=parse_iso_datetime(row["created_at"]),

        profile=profile_from_row(row),

        status=row["status"],

        providers=json.loads(row["providers"]),

        finding_count=row["finding_count"],

        risk_score=score,

    )

    settings.exports_dir.mkdir(parents=True, exist_ok=True)

    ext = body.format.lower()

    path = settings.exports_dir / f"cybermirror_{scan_id[:8]}.{ext}"

    intel = load_intelligence(scan_id)



    if ext == "json":

        export_json(summary, findings, path, intelligence=intel)

    elif ext == "csv":

        export_csv(findings, path)

    elif ext == "html":

        export_html(summary, findings, path, intelligence=intel)

    elif ext == "pdf":

        export_pdf(summary, findings, path, intelligence=intel)

    else:

        raise HTTPException(400, f"Unsupported format: {ext}")



    return {"path": str(path), "format": ext}





@router.get("/scans/{scan_id}/export/{format}/download")

def download_export(scan_id: str, format: str):

    data = get_scan(scan_id)

    if not data:

        raise HTTPException(404, "Scan not found")

    row = data["scan"]

    findings = [row_to_finding(f) for f in data["findings"]]

    score = sync_risk_score(row["id"], findings, stored=row["risk_score"])

    summary = ScanSummary(

        id=row["id"],

        created_at=parse_iso_datetime(row["created_at"]),

        profile=profile_from_row(row),

        status=row["status"],

        providers=json.loads(row["providers"]),

        finding_count=row["finding_count"],

        risk_score=score,

    )

    settings.exports_dir.mkdir(parents=True, exist_ok=True)

    ext = format.lower()

    path = settings.exports_dir / f"cybermirror_{scan_id[:8]}.{ext}"

    intel = load_intelligence(scan_id)



    if ext == "json":

        export_json(summary, findings, path, intelligence=intel)

    elif ext == "csv":

        export_csv(findings, path)

    elif ext == "html":

        export_html(summary, findings, path, intelligence=intel)

    elif ext == "pdf":

        export_pdf(summary, findings, path, intelligence=intel)

    else:

        raise HTTPException(400, f"Unsupported format: {ext}")



    if not path.exists():

        raise HTTPException(500, "Export failed")



    media = {

        "json": "application/json",

        "csv": "text/csv",

        "html": "text/html",

        "pdf": "application/pdf",

    }

    return FileResponse(

        path,

        media_type=media.get(ext, "application/octet-stream"),

        filename=path.name,

    )





def create_app():

    from fastapi import FastAPI

    from app.services.auth import ApiTokenMiddleware

    init_db()

    app = FastAPI(

        title=settings.app_name,

        description="CyberMirror — Native OSINT Self-Audit Engine",

        version=settings.app_version,

        lifespan=lifespan,

    )

    app.add_middleware(

        CORSMiddleware,

        allow_origins=["*"],

        allow_credentials=True,

        allow_methods=["*"],

        allow_headers=["*"],

    expose_headers=["*"],

    )

    if settings.api_auth_enabled:

        app.add_middleware(ApiTokenMiddleware)

    app.include_router(router)

    _mount_bundled_ui(app)

    return app


def _resolve_ui_dir():
    from pathlib import Path

    from app.config import PROJECT_ROOT

    for candidate in (
        PROJECT_ROOT / "frontend" / "dist" / "cybermirror" / "browser",
        PROJECT_ROOT / "frontend" / "dist",
    ):
        if (Path(candidate) / "index.html").is_file():
            return Path(candidate)
    return None


def _mount_bundled_ui(app) -> None:
    """Serve the Angular build with SPA fallback and same-origin API base hint."""
    import json

    from fastapi import HTTPException
    from fastapi.responses import FileResponse, HTMLResponse, Response

    ui_dir = _resolve_ui_dir()
    if ui_dir is None:
        return

    index_path = ui_dir / "index.html"
    ui_root = ui_dir.resolve()

    @app.get("/cybermirror-runtime.js")
    def cybermirror_runtime_js():
        # Same-origin API base only — never embed the bearer token (public GET).
        # Launcher/Electron inject window.cyberMirror.apiToken; Docker/manual use #api_token= or UI unlock.
        payload = {"apiBase": "/api"}
        body = (
            "window.cyberMirror=Object.assign(window.cyberMirror||{},"
            f"{json.dumps(payload)});"
        )
        return Response(
            content=body,
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    def _spa_index() -> HTMLResponse:
        html = index_path.read_text(encoding="utf-8")
        inject = '<script src="/cybermirror-runtime.js"></script>'
        if "cybermirror-runtime.js" not in html:
            html = html.replace("</head>", f"  {inject}\n</head>", 1)
        return HTMLResponse(html)

    @app.get("/")
    def ui_root_index():
        return _spa_index()

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path == "cybermirror-runtime.js":
            return cybermirror_runtime_js()

        target = (ui_dir / full_path).resolve()
        try:
            target.relative_to(ui_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found") from None

        if target.is_file():
            return FileResponse(target)
        return _spa_index()

