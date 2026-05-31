"""Local API token — prevents other processes from accessing CyberMirror API."""

import secrets
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import PROJECT_ROOT, settings

_TOKEN_FILE = PROJECT_ROOT / "data" / ".api_token"
PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


def get_or_create_token() -> str:
    if settings.api_token:
        return settings.api_token
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    _TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


class ApiTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.api_auth_enabled:
            return await call_next(request)
        path = request.url.path.rstrip("/") or "/"
        if path in PUBLIC_PATHS or not path.startswith("/api"):
            return await call_next(request)
        token = request.headers.get("X-CyberMirror-Token") or request.query_params.get("token")
        if token != get_or_create_token():
            return JSONResponse({"detail": "Invalid or missing API token"}, status_code=401)
        return await call_next(request)
