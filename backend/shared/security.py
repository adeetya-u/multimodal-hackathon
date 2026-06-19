"""HIPAA-oriented API safeguards — headers, audit trail, CORS tightening."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_logger = logging.getLogger(__name__)

PHI_PATH_PREFIXES = ("/api/cases", "/api/vapi", "/api/token")
SKIP_AUDIT_PATHS = ("/api/health", "/api/health/providers", "/docs", "/openapi.json", "/redoc")


def hipaa_mode() -> bool:
    return os.environ.get("HIPAA_MODE", "").strip().lower() in {"1", "true", "yes"}


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _is_phi_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PHI_PATH_PREFIXES)


def _should_audit(path: str, method: str) -> bool:
    if method in {"GET", "HEAD", "OPTIONS"}:
        return False
    if any(path.startswith(p) for p in SKIP_AUDIT_PATHS):
        return False
    return _is_phi_path(path)


def _extract_case_id(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "cases":
        return parts[2]
    return None


def _audit_rest(event: dict[str, Any]) -> None:
    """Best-effort audit insert via Insforge REST (service role)."""
    url = os.environ.get("INSFORGE_URL", "").strip().rstrip("/")
    key = os.environ.get("INSFORGE_SERVICE_KEY", "").strip()
    if not url or not key or os.environ.get("STORAGE_BACKEND", "").strip().lower() != "insforge":
        _logger.info("audit %s", json.dumps(event, default=str)[:500])
        return
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{url}/api/database/records/audit_events",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=[event],
            )
    except Exception as exc:
        _logger.warning("audit insert failed: %s", exc)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
        if hipaa_mode():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        elif _is_phi_path(request.url.path):
            response.headers.setdefault("Cache-Control", "no-store")

        if _should_audit(request.url.path, request.method):
            _audit_rest(
                {
                    "event_type": f"api.{request.method.lower()}",
                    "actor": "api",
                    "resource_type": "http",
                    "resource_id": request.url.path,
                    "case_id": _extract_case_id(request.url.path),
                    "ip_address": _client_ip(request),
                    "user_agent": (request.headers.get("user-agent") or "")[:256],
                    "metadata": {"status": response.status_code, "duration_ms": elapsed_ms},
                }
            )
        return response


def cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "*").strip()
    if hipaa_mode() and raw == "*":
        ui = os.environ.get("INSFORGE_UI_ORIGIN", "").strip()
        if ui:
            return [ui]
        _logger.warning("HIPAA_MODE: set CORS_ORIGINS or INSFORGE_UI_ORIGIN; falling back to permissive CORS")
    return [o.strip() for o in raw.split(",") if o.strip()]
