"""Shared case close + summary generation (agent and REST API)."""

from __future__ import annotations

import asyncio
import time

from .bootstrap import load_case_context
from .checklist import load_case_checklist
from .store import CaseStore, SessionLog
from .workers import run_summary

_close_locks: dict[str, asyncio.Lock] = {}


def _lock_for(case_id: str) -> asyncio.Lock:
    if case_id not in _close_locks:
        _close_locks[case_id] = asyncio.Lock()
    return _close_locks[case_id]


async def finalize_case(
    case_id: str,
    *,
    store: CaseStore,
    events: list[dict] | None = None,
    completed_steps: list[str] | None = None,
) -> SessionLog:
    """Generate operative summary and mark the case closed (idempotent)."""
    async with _lock_for(case_id):
        log = store.session_log(case_id)
        if log.is_closed:
            return log

        meta = store.get_metadata(case_id)
        ctx = load_case_context(case_id)
        if events is not None:
            log.events = events
        if completed_steps is not None:
            log.completed_steps = completed_steps
        else:
            checklist = load_case_checklist(case_id)
            log.completed_steps = [s.id for s in checklist.steps if s.status == "complete"]

        checklist_dict = load_case_checklist(case_id).to_dict()
        summary_md = await run_summary(
            patient_id=meta.patient_id,
            procedure=meta.procedure,
            checklist=checklist_dict,
            events=log.events,
            complications=[c.__dict__ for c in log.complications],
            mode_transitions=log.mode_transitions,
            transcript=log.transcript,
            patient_context=ctx.summary,
            manual_notes=meta.manual_notes or str(ctx.raw.get("manual_notes", "")),
            comorbidities=meta.comorbidities or list(ctx.raw.get("comorbidities") or []),
        )
        log.operative_summary = summary_md
        log.closed_at = time.time()
        store.save_session_log(case_id, log)
        return log
