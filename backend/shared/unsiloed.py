"""Unsiloed PDF parse client — submit async jobs, poll, and flatten responses."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import httpx

UNSILOED_PARSE_URL = os.environ.get(
    "UNSILOED_PARSE_URL", "https://prod.visionapi.unsiloed.ai/parse"
)
_DONE = frozenset({"succeeded", "success", "completed"})
_FAILED = frozenset({"failed", "error"})


def parse_timeout_sec() -> float:
    """Poll budget for async Unsiloed jobs (default 180s; override via UNSILOED_TIMEOUT)."""
    fast_fail = os.environ.get("UNSILOED_FAST_FAIL_SEC", "").strip()
    if fast_fail:
        return float(fast_fail)
    return float(os.environ.get("UNSILOED_TIMEOUT", "180"))


def extract_text(payload: dict[str, Any]) -> str:
    """Flatten Unsiloed parse payloads (sync or polled) into one markdown string."""
    direct = payload.get("markdown") or payload.get("text") or payload.get("content")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts: list[str] = []
    for chunk in payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        chunk_md = chunk.get("markdown") or chunk.get("embed") or chunk.get("text")
        if isinstance(chunk_md, str) and chunk_md.strip():
            parts.append(chunk_md.strip())
            continue
        for segment in chunk.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            seg_md = (
                segment.get("markdown")
                or segment.get("content")
                or segment.get("text")
                or ""
            )
            if isinstance(seg_md, str) and seg_md.strip():
                parts.append(seg_md.strip())
    return "\n\n".join(parts)


async def poll_job(
    client: httpx.AsyncClient,
    job_id: str,
    api_key: str,
    *,
    parse_url: str = UNSILOED_PARSE_URL,
) -> dict[str, Any]:
    poll_interval = float(os.environ.get("UNSILOED_POLL_INTERVAL", "3"))
    deadline = time.monotonic() + parse_timeout_sec()
    payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        poll = await client.get(f"{parse_url}/{job_id}", headers={"api-key": api_key})
        poll.raise_for_status()
        payload = poll.json()
        status = str(payload.get("status", "")).lower()
        if status in _DONE:
            return payload
        if status in _FAILED:
            raise RuntimeError(f"Unsiloed parse failed: {payload}")
    raise TimeoutError(
        f"Unsiloed parse timed out after {parse_timeout_sec():.0f}s (job {job_id})"
    )


async def parse_pdf(path: Path, api_key: str, *, parse_url: str = UNSILOED_PARSE_URL) -> str:
    """Submit a PDF to Unsiloed and return flattened markdown text."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        with path.open("rb") as f:
            submit = await client.post(
                parse_url,
                headers={"api-key": api_key},
                files={"file": (path.name, f, "application/pdf")},
            )
        submit.raise_for_status()
        payload = submit.json()
        job_id = payload.get("job_id")
        if job_id:
            payload = await poll_job(client, str(job_id), api_key, parse_url=parse_url)
        return extract_text(payload)
