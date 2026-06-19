"""Vapi server URL webhook orchestrator — runs surgical logger logic per utterance."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from .checklist import ChecklistState, load_case_checklist, merge_checklist_progress
from .bootstrap import load_case_context
from .chart_extract import try_chart_fact_answer
from .clinical_guard import guard_spoken_against_chart
from .search import (
    KnowledgeSearch,
    clear_display_payload,
    external_display_payload,
    find_grounded_snippet,
    grounded_display_payload,
    load_case_knowledge,
    merge_snippet_hits,
    rerank_snippets,
)
from .case_lifecycle import finalize_case
from .mode_controller import wants_close_case
from .session_sync import sync_session_state
from .storage import get_case_store
from .voice_events import voice_events
from .workers import (
    LoggerOutput,
    OperationMode,
    SessionState,
    apply_logger_output,
    build_session_context_block,
    expand_retrieval_query,
    run_answer,
    run_logger,
    run_nova_fallback_answer,
)

_logger = logging.getLogger(__name__)

# Per-call session state (case_id → state)
_sessions: dict[str, SessionState] = {}
_checklists: dict[str, ChecklistState] = {}
_knowledge: dict[str, KnowledgeSearch] = {}
_recent_utterances: dict[str, tuple[str, float]] = {}
_DEDUPE_WINDOW_SEC = 5.0


def _normalize_utterance(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _is_duplicate_utterance(case_id: str, text: str) -> bool:
    norm = _normalize_utterance(text)
    if not norm:
        return True
    now = time.time()
    prev = _recent_utterances.get(case_id)
    if prev and now - prev[1] < _DEDUPE_WINDOW_SEC:
        prev_norm = prev[0]
        if prev_norm == norm:
            return True
        # Ignore shorter prefix finals ("Patient's" then "Patient's allergies").
        if len(norm) < len(prev_norm) and prev_norm.startswith(norm):
            return True
        if len(norm) > len(prev_norm) and norm.startswith(prev_norm):
            _recent_utterances[case_id] = (norm, now)
            return False
    _recent_utterances[case_id] = (norm, now)
    return False


def _is_intro_message(body: dict[str, Any]) -> bool:
    call = body.get("call") or body.get("message", {}).get("call") or {}
    for raw in (
        call.get("metadata"),
        call.get("assistantOverrides", {}).get("metadata") if isinstance(call.get("assistantOverrides"), dict) else None,
        body.get("metadata"),
    ):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if isinstance(raw, dict) and str(raw.get("mode") or "").lower() == "intro":
            return True
    case_id = _case_id_from_message(body)
    return case_id in {"intro", "demo"}


def _case_id_from_message(body: dict[str, Any]) -> str | None:
    call = body.get("call") or body.get("message", {}).get("call") or {}
    assistant = body.get("assistant") or body.get("message", {}).get("assistant") or {}
    candidates: list[Any] = [
        call.get("metadata"),
        call.get("assistantOverrides", {}).get("metadata") if isinstance(call.get("assistantOverrides"), dict) else None,
        call.get("variableValues"),
        assistant.get("metadata"),
        assistant.get("variableValues"),
        body.get("metadata"),
        body.get("variableValues"),
        body.get("case_id"),
    ]
    for raw in candidates:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {"case_id": raw}
        if not isinstance(raw, dict):
            continue
        case_id = raw.get("case_id")
        if case_id:
            return str(case_id).strip()
    return None


def _transcript_is_final(msg: dict[str, Any]) -> bool:
    msg_type = str(msg.get("type") or "").lower()
    if "partial" in msg_type:
        return False
    transcript_type = str(msg.get("transcriptType") or msg.get("transcript_type") or "").lower()
    if transcript_type == "partial":
        return False
    if transcript_type == "final":
        return True
    return msg_type.startswith("transcript")


def _persist_checklist(case_id: str, checklist: ChecklistState) -> None:
    try:
        store = get_case_store()
        on_disk = load_case_checklist(case_id)
        merged = merge_checklist_progress(on_disk, checklist)
        store.write_json(case_id, "checklist.json", merged.to_dict())
        _checklists[case_id] = merged
    except Exception:
        _logger.exception("failed to persist checklist for %s", case_id)


def ensure_voice_session(case_id: str) -> tuple[SessionState, ChecklistState, KnowledgeSearch]:
    """Preload OR session state before the Vapi call starts."""
    return _get_session(case_id)


def _get_session(case_id: str) -> tuple[SessionState, ChecklistState, KnowledgeSearch]:
    if case_id not in _sessions:
        ctx = load_case_context(case_id)
        _sessions[case_id] = SessionState(session_id=case_id, patient_id=ctx.patient_id if ctx else "")
        _checklists[case_id] = load_case_checklist(case_id)
        _knowledge[case_id] = load_case_knowledge(case_id)
    return _sessions[case_id], _checklists[case_id], _knowledge[case_id]


def _context_block(case_id: str, state: SessionState, checklist: ChecklistState) -> str:
    ctx = load_case_context(case_id)
    current = next((s for s in checklist.steps if s.status == "in_progress"), None)
    active = current.label if current else ""
    return build_session_context_block(
        ctx.summary if ctx else "",
        state,
        phase=state.phase,
        active_step=active,
    )


def _guard_spoken(case_id: str, spoken: str) -> str:
    ctx = load_case_context(case_id)
    return guard_spoken_against_chart(
        spoken,
        ctx.summary if ctx else "",
        raw_context=ctx.raw if ctx else None,
    )


def _publish_agent_mode(
    case_id: str,
    state: SessionState,
    *,
    logger_out: LoggerOutput | None = None,
) -> None:
    """Map backend session state to UI agent-mode SSE."""
    if logger_out and logger_out.needs_retrieval and logger_out.mode == "query":
        mode = "situation" if state.active_situation is not None else "query"
    elif state.mode == OperationMode.SITUATION or state.active_situation is not None:
        mode = "situation"
    else:
        mode = "logger"
    voice_events.publish(case_id, "agent-mode", {"mode": mode, "updated_at": time.time()})


async def _run_answer_pipeline(
    case_id: str,
    query: str,
    *,
    prefer_sop: bool = False,
    segment: str = "",
) -> str:
    state, checklist, knowledge = _get_session(case_id)
    ctx = load_case_context(case_id)
    voice_events.publish(case_id, "agent-status", {"status": "searching", "ts": time.time()})

    chart_spoken = try_chart_fact_answer(query, ctx)
    if chart_spoken:
        voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
        return _guard_spoken(case_id, chart_spoken)

    search_query = expand_retrieval_query(state, query, segment or query)
    if re.search(r"\bmedications?\b|\bmeds\b|\bhome meds\b", query, re.I):
        search_query = f"{search_query} medications pre-admission home medications"
    patient_hits = await knowledge.search(search_query, k=6, prefer_patient=True)
    if prefer_sop and ctx:
        ref_hits = await knowledge.search(
            f"{search_query} {ctx.procedure}".strip(), k=6, prefer_sop=True, prefer_patient=False
        )
        candidates = merge_snippet_hits(patient_hits, ref_hits, limit=8)
    else:
        candidates = patient_hits
    survivors = rerank_snippets(query, candidates, prefer_patient=not prefer_sop)
    live_context = _context_block(case_id, state, checklist)
    if survivors:
        answer = await run_answer(query, survivors, live_context=live_context)
        if not answer.refusal and answer.grounded_ids:
            grounded = find_grounded_snippet(survivors, answer.grounded_ids)
            if grounded:
                spoken = _guard_spoken(case_id, answer.spoken_text)
                display = grounded_display_payload(
                    grounded, spoken_text=spoken, confidence=grounded.score
                )
                voice_events.publish(case_id, "grounded-display", display)
                voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
                return spoken
        if answer.spoken_text.strip() and not answer.refusal:
            voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
            return _guard_spoken(case_id, answer.spoken_text)

    fallback = await run_nova_fallback_answer(
        query,
        live_context=live_context,
        procedure=ctx.procedure if ctx else "",
        hints=survivors,
    )
    if fallback.spoken_text.strip():
        grounded = find_grounded_snippet(survivors, fallback.grounded_ids) if fallback.grounded_ids else None
        if grounded:
            spoken = _guard_spoken(case_id, fallback.spoken_text)
            display = grounded_display_payload(
                grounded, spoken_text=spoken, confidence=grounded.score
            )
            voice_events.publish(case_id, "grounded-display", display)
            voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
            return spoken
        spoken = _guard_spoken(case_id, fallback.spoken_text)
        voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
        return spoken

    voice_events.publish(case_id, "grounded-display", clear_display_payload())
    voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
    return _guard_spoken(case_id, "I don't have a grounded answer in the case file.")


async def process_surgeon_utterance(case_id: str, text: str) -> dict[str, Any]:
    """Process one final surgeon utterance; persist checklist and return UI payload."""
    cleaned = text.strip()
    if not cleaned:
        return {"ok": False, "spoken": "", "checklist": load_case_checklist(case_id).to_dict()}
    if _is_duplicate_utterance(case_id, cleaned):
        _, checklist, _ = _get_session(case_id)
        return {"ok": True, "spoken": "", "duplicate": True, "checklist": checklist.to_dict()}
    spoken, closed = await handle_transcript(case_id, cleaned)
    _, checklist, _ = _get_session(case_id) if not closed else (None, load_case_checklist(case_id), None)
    if not closed:
        _persist_checklist(case_id, checklist)
    return {
        "ok": True,
        "spoken": spoken,
        "checklist": checklist.to_dict(),
        "close_case": closed,
    }


def _dialogue_transcript(state: SessionState) -> list[dict[str, Any]]:
    return [{"role": turn.role, "text": turn.text, "ts": turn.ts} for turn in state.dialogue]


async def _close_case_from_voice(
    case_id: str,
    state: SessionState,
    checklist: ChecklistState,
    text: str,
) -> str:
    spoken = "Closing the case and generating your summary."
    state.append_dialogue("surgeon", text)
    state.append_dialogue("agent", spoken)

    voice_events.publish(case_id, "agent-mode", {"mode": "summary", "updated_at": time.time()})
    voice_events.publish(case_id, "agent-status", {"status": "closing", "ts": time.time()})
    voice_events.publish(
        case_id,
        "transcript",
        {"id": f"agent-{time.time()}", "role": "agent", "text": spoken, "ts": time.time()},
    )
    voice_events.publish(case_id, "grounded-display", clear_display_payload())

    store = get_case_store()
    sync_session_state(
        case_id,
        store=store,
        checklist=checklist.to_dict(),
        transcript=_dialogue_transcript(state),
    )
    _persist_checklist(case_id, checklist)
    await finalize_case(case_id, store=store)
    voice_events.publish(case_id, "case-closed", {"case_id": case_id, "ts": time.time()})

    _sessions.pop(case_id, None)
    _checklists.pop(case_id, None)
    _knowledge.pop(case_id, None)

    return spoken


async def handle_transcript(case_id: str, text: str) -> tuple[str, bool]:
    """Process surgeon utterance; return spoken response and whether the case was closed."""
    state, checklist, knowledge = _get_session(case_id)
    voice_events.publish(
        case_id,
        "transcript",
        {"id": f"surgeon-{time.time()}", "role": "surgeon", "text": text, "ts": time.time()},
    )
    voice_events.publish(case_id, "agent-status", {"status": "thinking", "ts": time.time()})

    if wants_close_case(text):
        spoken = await _close_case_from_voice(case_id, state, checklist, text)
        return spoken, True

    state.append_dialogue("surgeon", text)
    context = _context_block(case_id, state, checklist)

    logger_out = await run_logger(
        state=state,
        checklist=checklist,
        segment=text,
        context_block=context,
    )
    apply_logger_output(state, logger_out, checklist)
    knowledge.sync_live_events([(e.type, e.text) for e in state.compacted_events()])

    voice_events.publish(case_id, "surgical-checklist", checklist.to_dict())
    _publish_agent_mode(case_id, state, logger_out=logger_out)

    if logger_out.needs_retrieval:
        query = logger_out.extracted_query or text
        prefer_sop = state.active_situation is not None or state.mode == OperationMode.SITUATION
        was_situation = state.active_situation is not None or state.mode == OperationMode.SITUATION
        spoken = await _run_answer_pipeline(case_id, query, prefer_sop=prefer_sop, segment=text)
        state.mode = OperationMode.SITUATION if was_situation else OperationMode.LOGGING
        _publish_agent_mode(case_id, state)
    else:
        voice_events.publish(case_id, "grounded-display", clear_display_payload())
        spoken = "Noted."

    state.append_dialogue("agent", spoken)
    voice_events.publish(
        case_id,
        "transcript",
        {"id": f"agent-{time.time()}", "role": "agent", "text": spoken, "ts": time.time()},
    )
    voice_events.publish(case_id, "agent-status", {"status": "idle", "ts": time.time()})
    voice_events.publish(case_id, "case-bootstrap-ack", {"ok": True, "case_id": case_id})
    return spoken, False


async def handle_vapi_webhook(body: dict[str, Any]) -> dict[str, Any]:
    """Entry point for POST /api/vapi/webhook."""
    if _is_intro_message(body):
        return {"ok": True}

    msg = body.get("message") or body
    msg_type = str(msg.get("type") or body.get("type") or "").lower()

    if msg_type in {"assistant-request", "assistant-request-message"}:
        case_id = _case_id_from_message(body)
        if case_id:
            _, checklist, _ = _get_session(case_id)
            return {
                "assistant": {
                    "firstMessage": "Scalpel is ready. Report a checklist step or ask a clinical question.",
                    "model": {
                        "provider": "custom-llm",
                        "url": os.environ.get("VAPI_SERVER_URL", "").rstrip("/") + "/api/vapi/llm",
                    },
                    "metadata": {"case_id": case_id},
                }
            }
        return {}

    if msg_type in {"transcript", "speech-update"} or str(msg_type).lower().startswith("transcript"):
        role = str(msg.get("role") or "").lower()
        text = str(msg.get("transcript") or msg.get("text") or "").strip()
        if role == "user" and text and _transcript_is_final(msg):
            case_id = _case_id_from_message(body)
            if not case_id:
                return {"message": {"type": "say", "content": "No case context."}}
            result = await process_surgeon_utterance(case_id, text)
            spoken = str(result.get("spoken") or "").strip()
            if spoken:
                return {"message": {"type": "say", "content": spoken}}
            return {"ok": True}

    if msg_type == "end-of-call-report":
        case_id = _case_id_from_message(body)
        if case_id and case_id in _sessions:
            del _sessions[case_id]
            _checklists.pop(case_id, None)
            _knowledge.pop(case_id, None)
        return {"ok": True}

    return {"ok": True}
