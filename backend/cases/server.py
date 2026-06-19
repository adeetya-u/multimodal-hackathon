"""REST API — cases, ingestion, Vapi voice, summary."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from shared.security import SecurityHeadersMiddleware, cors_origins, hipaa_mode

from .bootstrap import bootstrap_to_gzip, build_bootstrap_payload, load_case_context
from .case_lifecycle import finalize_case
from .checklist import ensure_case_checklist, load_case_checklist
from .session_sync import sync_session_state
from .pipeline import regenerate_case_checklist, run_ingestion_pipeline
from .provider_checks import run_provider_checks
from .storage import get_case_store
from .voice import voice_start_payload, voice_status
from .vapi_webhooks import ensure_voice_session, handle_vapi_webhook, process_surgeon_utterance
from .voice_events import voice_events
from .workers import run_summary
from .store import (
    CaseEventHub,
    IngestionStage,
    SessionLog,
    build_case_status,
    case_data_root,
    sse_encode,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Scalpel API", version="2.0.0")
_case_events = CaseEventHub()


def _publish(case_id: str) -> None:
    _case_events.publish(case_id, build_case_status(_store, case_id))


_store = get_case_store(on_change=_publish)

_origins = cors_origins() if hipaa_mode() else os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)


class CreateCaseRequest(BaseModel):
    patient_id: str
    procedure: str = "Total Knee Arthroplasty, right knee"
    manual_notes: str = ""
    comorbidities: list[str] = Field(default_factory=list)


class UpdateCaseRequest(BaseModel):
    patient_id: str
    procedure: str
    manual_notes: str = ""
    comorbidities: list[str] = Field(default_factory=list)


class ChecklistStepInput(BaseModel):
    id: str
    label: str
    aliases: list[str] = Field(default_factory=list)


class ChecklistUpdateRequest(BaseModel):
    procedure: str | None = None
    steps: list[ChecklistStepInput]


class StepProgressRequest(BaseModel):
    status: str


class VoiceUtteranceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class SessionSyncRequest(BaseModel):
    checklist: dict | None = None
    transcript: list[dict] | None = None
    events: list[dict] | None = None
    completed_steps: list[str] | None = None


class TokenRequest(BaseModel):
    room: str | None = None
    participant_name: str = Field(default="or-display")
    participant_identity: str | None = None
    case_id: str | None = None
    intro: bool = False


class TokenResponse(BaseModel):
    token: str
    url: str
    room: str
    identity: str
    case_id: str | None = None


def _read_checklist(case_id: str) -> dict:
    path = _store.case_dir(case_id) / "checklist.json"
    if path.exists():
        return _store.read_json(case_id, "checklist.json")
    meta = _store.get_metadata(case_id)
    return {"procedure": meta.procedure, "mode": "logger", "steps": []}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "scalpel-api", "voice": "vapi"}


@app.get("/api/health/providers")
async def health_providers(case_id: str | None = None, deep: bool = True) -> dict:
    """Live checks for Nebius, Vapi, Insforge, and optional case."""
    return await run_provider_checks(case_id=case_id, deep=deep)


@app.get("/api/cases/{case_id}/voice-readiness")
async def voice_readiness(case_id: str) -> dict:
    """Voice-path checks — Vapi configuration."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = voice_status()
    result["case_id"] = case_id
    return result


@app.get("/api/cases/{case_id}/voice-agent")
async def voice_agent_status(case_id: str) -> dict:
    """Lightweight agent presence check for prep/OR warmup polling."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status = voice_status()
    return {"ok": True, "case_id": case_id, **status}


@app.get("/api/voice/diagnostics")
async def voice_diagnostics(case_id: str | None = None) -> dict:
    """Voice pipeline diagnostics."""
    return {"provider": "vapi", **voice_status(), "case_id": case_id}


@app.post("/api/cases")
def create_case(body: CreateCaseRequest) -> dict:
    return _store.create_case(
        patient_id=body.patient_id,
        procedure=body.procedure,
        manual_notes=body.manual_notes,
        comorbidities=body.comorbidities,
    ).to_dict()


@app.get("/api/cases")
def list_cases() -> list[dict]:
    return [c.to_dict() for c in _store.list_cases()]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    try:
        return _store.get_metadata(case_id).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/cases/{case_id}")
def update_case(case_id: str, body: UpdateCaseRequest) -> dict:
    try:
        return _store.update_case_details(
            case_id,
            patient_id=body.patient_id,
            procedure=body.procedure,
            manual_notes=body.manual_notes,
            comorbidities=body.comorbidities,
        ).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str) -> dict:
    try:
        _store.delete_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "case_id": case_id}


@app.get("/api/cases/{case_id}/status")
def get_case_status(case_id: str) -> dict:
    try:
        return build_case_status(_store, case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/cases/{case_id}/events")
async def stream_case_events(case_id: str) -> StreamingResponse:
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_stream():
        queue = _case_events.subscribe(case_id)
        try:
            payload = build_case_status(_store, case_id)
            yield sse_encode(payload)
            terminal = {IngestionStage.READY.value, IngestionStage.ERROR.value}
            if payload["case"]["stage"] in terminal:
                return
            while True:
                payload = await queue.get()
                yield sse_encode(payload)
                if payload["case"]["stage"] in terminal:
                    break
        finally:
            _case_events.unsubscribe(case_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/cases/{case_id}/checklist/generate")
async def generate_case_checklist(case_id: str) -> dict:
    """Generate pre/intra/post-op milestones from patient chart + SOP reference (Bedrock)."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        checklist = await regenerate_case_checklist(_store, case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("checklist generation failed for %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _publish(case_id)
    return checklist


@app.put("/api/cases/{case_id}/checklist")
def replace_case_checklist(case_id: str, body: ChecklistUpdateRequest) -> dict:
    try:
        current = _read_checklist(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if len(body.steps) < 1:
        raise HTTPException(status_code=400, detail="Checklist must have at least one step")
    payload = {
        "procedure": body.procedure or current.get("procedure") or _store.get_metadata(case_id).procedure,
        "mode": "logger",
        "steps": [s.model_dump() for s in body.steps],
    }
    _store.write_json(case_id, "checklist.json", payload)
    _publish(case_id)
    return payload


@app.post("/api/cases/{case_id}/checklist/steps/{step_id}/progress")
def advance_checklist_step(case_id: str, step_id: str, body: StepProgressRequest) -> dict:
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status = body.status.strip().lower()
    if status in {"completed", "complete"}:
        step_status = "complete"
    elif status == "in_progress":
        step_status = "in_progress"
    else:
        raise HTTPException(status_code=400, detail="status must be in_progress or complete")
    checklist = load_case_checklist(case_id)
    try:
        applied = checklist.apply_step_update(step_id, step_status)  # type: ignore[arg-type]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if applied is None:
        raise HTTPException(status_code=400, detail="Cannot go back or invalid step transition")
    payload = checklist.to_dict()
    _store.write_json(case_id, "checklist.json", payload)
    return payload


@app.post("/api/cases/{case_id}/documents")
async def upload_document(
    case_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict:
    try:
        meta = _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raw_dir = _store.case_dir(case_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / (file.filename or f"upload-{uuid.uuid4().hex[:8]}.pdf")
    dest.write_bytes(await file.read())
    _store.set_single_document(case_id, dest.name)
    if meta.stage in (IngestionStage.PARSING, IngestionStage.COMPACTING, IngestionStage.INDEXING):
        return {
            "filename": dest.name,
            "case_id": case_id,
            "replaced": True,
            "stage": meta.stage.value,
            "message": "Already processing",
        }
    _store.update_stage(case_id, IngestionStage.PARSING)
    background_tasks.add_task(_run_pipeline, case_id)
    return {
        "filename": dest.name,
        "case_id": case_id,
        "replaced": True,
        "stage": IngestionStage.PARSING.value,
        "message": "Ingestion started",
    }


@app.post("/api/cases/{case_id}/prepare")
async def prepare_case(case_id: str, background_tasks: BackgroundTasks) -> dict:
    try:
        meta = _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if meta.stage in (IngestionStage.PARSING, IngestionStage.COMPACTING, IngestionStage.INDEXING):
        return {"case_id": case_id, "stage": meta.stage.value, "message": "Already processing"}
    _store.update_stage(case_id, IngestionStage.PARSING)
    background_tasks.add_task(_run_pipeline, case_id)
    return {"case_id": case_id, "stage": IngestionStage.PARSING.value, "message": "Ingestion started"}


async def _run_pipeline(case_id: str) -> None:
    try:
        await run_ingestion_pipeline(_store, case_id)
    except Exception as exc:
        logger.exception("pipeline failed for %s", case_id)
        _store.update_stage(case_id, IngestionStage.ERROR, str(exc))


@app.get("/api/cases/{case_id}/summary")
def get_case_summary(case_id: str) -> dict:
    try:
        meta = _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log: SessionLog = _store.session_log(case_id)
    if not log.is_closed:
        return {
            "status": "in_progress",
            "case": meta.to_dict(),
            "patient": {"id": meta.patient_id, "procedure": meta.procedure},
            "transcript_turns": len(log.transcript),
        }
    checklist = _read_checklist(case_id)
    steps = checklist.get("steps", [])
    ctx = load_case_context(case_id)
    return {
        "status": "closed",
        "case": meta.to_dict(),
        "patient": {"id": meta.patient_id, "procedure": meta.procedure},
        "checklist": checklist,
        "completed_steps": log.completed_steps,
        "complications": [c.__dict__ for c in log.complications],
        "events": log.events,
        "transcript": log.transcript,
        "mode_transitions": log.mode_transitions,
        "operative_summary": log.operative_summary,
        "closed_at": log.closed_at,
        "patient_context": ctx.summary,
        "stats": {
            "steps_completed": len(log.completed_steps),
            "total_steps": len(steps),
            "complications": len(log.complications),
            "queries": sum(1 for e in log.events if e.get("type") == "query"),
            "events": len(log.events),
            "transcript_turns": len(log.transcript),
        },
    }


async def _generate_case_summary(case_id: str) -> str:
    meta = _store.get_metadata(case_id)
    ctx = load_case_context(case_id)
    log = _store.session_log(case_id)
    checklist = _read_checklist(case_id)
    return await run_summary(
        patient_id=meta.patient_id,
        procedure=meta.procedure,
        checklist=checklist,
        events=log.events,
        complications=[c.__dict__ for c in log.complications],
        mode_transitions=log.mode_transitions,
        transcript=log.transcript,
        patient_context=ctx.summary,
        manual_notes=meta.manual_notes,
        comorbidities=meta.comorbidities,
    )


@app.post("/api/cases/{case_id}/summary/generate")
async def generate_case_summary(case_id: str) -> dict:
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log = _store.session_log(case_id)
    log.operative_summary = await _generate_case_summary(case_id)
    if not log.closed_at:
        log.closed_at = time.time()
    _store.save_session_log(case_id, log)
    return get_case_summary(case_id)


@app.get("/api/checklist")
def get_checklist(case_id: str | None = None) -> dict:
    return load_case_checklist(case_id).to_dict()


@app.post("/api/cases/{case_id}/warm-voice")
async def warm_voice_agent(case_id: str, force: bool = False, reset: bool = False) -> dict:
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _, checklist_seeded = ensure_case_checklist(_store, case_id)
    payload = voice_start_payload(case_id)
    return {
        "ok": True,
        "case_id": case_id,
        "provider": "vapi",
        "dispatched": True,
        "checklist_seeded": checklist_seeded,
        **payload,
    }


@app.post("/api/cases/{case_id}/session/sync")
def sync_case_session(case_id: str, body: SessionSyncRequest) -> dict:
    """Merge live OR transcript/checklist/events from browser or cloud agent."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log = sync_session_state(
        case_id,
        store=_store,
        checklist=body.checklist,
        transcript=body.transcript,
        events=body.events,
        completed_steps=body.completed_steps,
    )
    return {
        "ok": True,
        "transcript_turns": len(log.transcript),
        "events": len(log.events),
        "completed_steps": len(log.completed_steps),
    }


@app.post("/api/cases/{case_id}/close")
async def close_case(case_id: str) -> dict:
    """Finalize summary, mark case closed, and end voice session."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await finalize_case(case_id, store=_store)
    return get_case_summary(case_id)


@app.post("/api/cases/{case_id}/voice-leave")
async def voice_leave(case_id: str) -> dict:
    """End voice session for a case."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "case_id": case_id, "provider": "vapi"}


@app.get("/api/cases/{case_id}/bootstrap")
def get_case_bootstrap(case_id: str) -> Response:
    try:
        payload = build_bootstrap_payload(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=bootstrap_to_gzip(payload), media_type="application/gzip", headers={"Cache-Control": "no-store"})


def _resolve_token_case_id(body_case_id: str | None) -> str | None:
    case_id = (body_case_id or "").strip() or None
    if case_id:
        return case_id
    if os.environ.get("SCALPEL_ALLOW_ACTIVE_CASE_FALLBACK", "0").strip().lower() in {"1", "true", "yes"}:
        return os.environ.get("ACTIVE_CASE_ID", "").strip() or None
    return None


@app.post("/api/cases/{case_id}/voice/start")
async def start_voice_session(case_id: str) -> dict:
    """Return Vapi client config to start an OR voice call."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ensure_case_checklist(_store, case_id)
    ensure_voice_session(case_id)
    return {"ok": True, **voice_start_payload(case_id)}


@app.post("/api/cases/{case_id}/voice/utterance")
async def voice_utterance(case_id: str, body: VoiceUtteranceRequest) -> dict:
    """Process a final surgeon utterance — checklist progress + clinical routing."""
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await process_surgeon_utterance(case_id, body.text)


@app.get("/api/cases/{case_id}/voice-status")
async def case_voice_status(case_id: str) -> dict:
    try:
        _store.get_metadata(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "case_id": case_id, **voice_status()}


@app.post("/api/vapi/webhook")
async def vapi_webhook(request: Request) -> dict:
    body = await request.json()
    return await handle_vapi_webhook(body)


@app.get("/api/cases/{case_id}/voice/stream")
async def voice_event_stream(case_id: str) -> StreamingResponse:
    """SSE bridge: Vapi webhook events → OR UI."""

    async def generate():
        queue = voice_events.subscribe(case_id)
        try:
            yield sse_encode({"topic": "connected", "payload": {"case_id": case_id}})
            while True:
                event = await queue.get()
                yield sse_encode(event)
        finally:
            voice_events.unsubscribe(case_id, queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/token", response_model=TokenResponse)
async def create_token(body: TokenRequest) -> TokenResponse:
    case_id = _resolve_token_case_id(body.case_id)
    if body.intro:
        from .voice import intro_assistant_id, public_key

        return TokenResponse(
            token="",
            url="",
            room="vapi-intro",
            identity=body.participant_identity or "intro-user",
            case_id=None,
        )
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    payload = voice_start_payload(case_id)
    return TokenResponse(
        token=payload.get("publicKey", ""),
        url="vapi",
        room=f"vapi-{case_id}",
        identity=body.participant_identity or "or-user",
        case_id=case_id,
    )


@app.post("/api/intro/warmup")
async def intro_warmup(fresh: bool = False) -> dict:
    """Prep intro assistant — Vapi config for landing demo."""
    from .voice import intro_assistant_id, intro_assistant_overrides, public_key

    return {
        "ok": True,
        "provider": "vapi",
        "assistantId": intro_assistant_id(),
        "publicKey": public_key(),
        "dispatched": bool(intro_assistant_id()),
        "assistantOverrides": intro_assistant_overrides(),
    }


@app.post("/api/intro/utterance")
async def intro_utterance(body: VoiceUtteranceRequest) -> dict:
    """Answer a general knee question — reference corpus only, no patient chart."""
    from .intro_voice import answer_intro_question

    spoken = await answer_intro_question(body.text)
    return {"ok": True, "spoken": spoken}


def main() -> None:
    import shared.bootstrap  # noqa: F401

    case_data_root().mkdir(parents=True, exist_ok=True)
    from .dev_lock import acquire_api_lock

    acquire_api_lock()
    import uvicorn

    host = os.environ.get("SCALPEL_API_HOST", os.environ.get("SURGICAL_HOST", "0.0.0.0"))
    port = int(os.environ.get("PORT", os.environ.get("SCALPEL_API_PORT", os.environ.get("SURGICAL_PORT", "3001"))))
    uvicorn.run("services.api.main:app", host=host, port=port, reload=os.environ.get("SURGICAL_RELOAD", "0") == "1")


if __name__ == "__main__":
    main()
