"""Merge OR session state into the API case store (cloud agent + browser → summary)."""

from __future__ import annotations

import logging
import os
from typing import Any

from .checklist import ChecklistState, merge_checklist_progress, load_case_checklist
from .store import CaseStore, SessionLog
from .time_utils import normalize_transcript_turns

logger = logging.getLogger(__name__)


def _prefer_longer(existing: list[dict], incoming: list[dict]) -> list[dict]:
    return incoming if len(incoming) >= len(existing) else existing


def sync_session_state(
    case_id: str,
    *,
    store: CaseStore,
    checklist: dict[str, Any] | None = None,
    transcript: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    completed_steps: list[str] | None = None,
) -> SessionLog:
    """Merge live OR progress into on-disk session_log + checklist (never drop longer transcripts)."""
    log = store.session_log(case_id)

    if transcript is not None:
        log.transcript = normalize_transcript_turns(
            _prefer_longer(log.transcript, transcript)
        )
    if events is not None:
        log.events = _prefer_longer(log.events, events)
    if completed_steps is not None:
        log.completed_steps = completed_steps

    if checklist is not None:
        case_dir = store.case_dir(case_id)
        if (case_dir / "checklist.json").exists():
            current = load_case_checklist(case_id)
            incoming = ChecklistState.from_dict(checklist)
            merged = merge_checklist_progress(current, incoming)
            store.write_json(case_id, "checklist.json", merged.to_dict())
        else:
            store.write_json(case_id, "checklist.json", checklist)

    if completed_steps is None and checklist is not None:
        steps = checklist.get("steps", [])
        log.completed_steps = [
            str(s["id"]) for s in steps if isinstance(s, dict) and s.get("status") in {"complete", "completed"}
        ]

    store.save_session_log(case_id, log)
    return log


def surgical_api_base() -> str:
    return os.environ.get("SURGICAL_API_URL", "").strip().rstrip("/")


async def post_session_sync(case_id: str, payload: dict[str, Any]) -> bool:
    """Push session snapshot from cloud agent to the local/API case store."""
    base = surgical_api_base()
    if not base:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{base}/api/cases/{case_id}/session/sync", json=payload)
            res.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("session sync POST failed for %s: %s", case_id, exc)
        return False


async def post_close_case(case_id: str) -> bool:
    base = surgical_api_base()
    if not base:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(f"{base}/api/cases/{case_id}/close")
            res.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("close case POST failed for %s: %s", case_id, exc)
        return False
