from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime
import time
from dataclasses import dataclass, field
from enum import Enum

from .llm import converse_text, resolve_model
from .time_utils import format_epoch_ts, normalize_epoch_ts, normalize_transcript_turns
from .checklist import (
    ChecklistState,
    INFERENCE_CONFIDENCE_THRESHOLD,
    StepInference,
    infer_step_update_from_transcript,
    infer_step_update_scored,
    segment_reports_checklist_progress,
    segment_reports_completion,
)
from .checklist_mark import assess_checklist_mark
from .mode_controller import COMPLICATION_PATTERNS, RESOLVED_PATTERNS, _matches_any
from .prompts import build_answer_prompt, build_nova_fallback_prompt, build_summary_prompt
from .types import Snippet
from .utterance_intent import (
    SegmentIntent,
    SegmentIntentKind,
    classify_intent_for_utterance,
    classify_segment_intent,
    is_explicit_question,
)

REFUSAL_A_TEMPLATE = "I don't have that in the chart."
_GROUNDED_RE = re.compile(r"^GROUNDED:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def _format_ts(ts: float | int | None) -> str:
    formatted = format_epoch_ts(ts)
    return formatted or "00:00:00"


def _format_transcript_lines(transcript: list[dict]) -> list[str]:
    lines: list[str] = []
    for turn in normalize_transcript_turns(transcript):
        if turn.get("interim"):
            continue
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        role = str(turn.get("role", "unknown"))
        label = "Surgeon" if role == "surgeon" else "Agent" if role == "agent" else role.title()
        ts = normalize_epoch_ts(turn.get("ts"))
        prefix = f"[{_format_ts(ts)}] " if ts else ""
        lines.append(f"{prefix}{label}: {text}")
    return lines


def normalize_summary_markdown(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_summary_sections(markdown: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for chunk in markdown.split("## "):
        chunk = chunk.strip()
        if not chunk:
            continue
        title, _, body = chunk.partition("\n")
        sections.append({"title": title.strip(), "body": body.strip()})
    return sections


def _summary_has_required_sections(markdown: str) -> bool:
    titles = {section["title"] for section in parse_summary_sections(markdown)}
    return "Procedure" in titles and len(titles) >= 4

class OperationMode(str, Enum):
    LOGGING = "logging"
    SITUATION = "situation"
    QUERY = "query"


@dataclass
class ActiveSituation:
    summary: str
    opened_at: float


@dataclass
class EventRecord:
    ts: float
    type: str
    text: str
    source: str | None = None


@dataclass
class DialogueTurn:
    role: str
    text: str
    ts: float


@dataclass
class SessionState:
    session_id: str
    patient_id: str
    mode: OperationMode = OperationMode.LOGGING
    phase: str = ""
    active_situation: ActiveSituation | None = None
    event_log: list[EventRecord] = field(default_factory=list)
    dialogue: list[DialogueTurn] = field(default_factory=list)

    def append_event(self, event_type: str, text: str) -> None:
        cleaned = _compact_text(text)
        if not cleaned:
            return
        self.event_log.append(EventRecord(ts=time.time(), type=event_type, text=cleaned))
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]

    def append_dialogue(self, role: str, text: str, *, limit: int = 500) -> None:
        cleaned = _compact_text(text, limit=limit)
        if not cleaned:
            return
        normalized = "surgeon" if role == "surgeon" else "agent"
        self.dialogue.append(DialogueTurn(role=normalized, text=cleaned, ts=time.time()))
        if len(self.dialogue) > 80:
            self.dialogue = self.dialogue[-80:]

    def compacted_events(self) -> list[EventRecord]:
        return self.event_log


def _compact_text(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class LoggerOutput:
    mode: str = "logging"
    situation_resolved: bool = False
    phase: str = ""
    step_update: dict[str, str] | None = None
    events: list[str] | None = None
    extracted_query: str | None = None
    needs_retrieval: bool = False


@dataclass
class AnswerResult:
    grounded_ids: list[str]
    spoken_text: str
    refusal: bool = False
    external: bool = False
    external_source: str = ""
    external_excerpt: str = ""


def sanitize_spoken_output(text: str) -> str:
    """Strip model thinking tags and prompt echoes before TTS."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(
        r"<\s*redacted_thinking\s*>.*?<\s*/\s*redacted_thinking\s*>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(r"<\s*redacted_thinking\s*>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<\s*/?\s*redacted_thinking\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<\s*think\s*>.*?<\s*/\s*think\s*>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"The user says:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"knee orthopedics assistant\.?\s*one or two short spoken sentences\.?\s*never refuse\.?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:Q|A):\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r"GROUNDED:\s*(?:NONE|\[[^\]]*\])\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned.replace("\n", " ")).strip()
    lower = cleaned.lower()
    if not cleaned:
        return ""
    if lower.startswith("knee orthopedics assistant"):
        return ""
    if "one or two short spoken sentences" in lower and len(cleaned) < 140:
        return ""
    return cleaned


def clamp_spoken_text(text: str, *, max_lines: int | None = None, max_chars: int | None = None) -> str:
    def _limit(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    if max_lines is None:
        max_lines = _limit("SPOKEN_MAX_LINES", 3)
    if max_chars is None:
        max_chars = _limit("SPOKEN_MAX_CHARS", 360)
    cleaned = sanitize_spoken_output(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s+", " ", cleaned.replace("\n", " ")).strip()
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    lines: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        lines.append(sentence)
        if len(lines) >= max_lines:
            break
    result = " ".join(lines) if lines else cleaned
    if len(result) > max_chars:
        result = result[: max_chars - 1].rstrip() + "…"
    return result


def _apply_high_confidence_inference(
    output: LoggerOutput,
    checklist: ChecklistState,
    segment: str,
    *,
    intent: SegmentIntent | None = None,
) -> LoggerOutput:
    scored = infer_step_update_scored(checklist, segment)
    if not scored or scored.confidence < INFERENCE_CONFIDENCE_THRESHOLD:
        return output
    if intent and intent.is_question and scored.confidence < 0.72:
        return output
    inferred = {"step": scored.step_label, "status": scored.status}
    llm_step = (output.step_update or {}).get("step", "") if isinstance(output.step_update, dict) else ""
    if not output.step_update or llm_step.strip().lower() == scored.step_label.lower():
        output.step_update = inferred
    if intent and intent.is_question and not intent.is_checklist:
        return output
    output.needs_retrieval = False
    if output.mode == "query":
        output.mode = "logging"
    return output


def _logger_output_from_intent(intent: SegmentIntent, segment: str, *, state: SessionState) -> LoggerOutput | None:
    compact = _compact_text(segment)
    if intent.kind == SegmentIntentKind.QUESTION:
        return LoggerOutput(
            mode="query",
            needs_retrieval=True,
            extracted_query=intent.extracted_query or segment,
            events=[compact],
        )
    if intent.kind == SegmentIntentKind.SITUATION:
        return LoggerOutput(
            mode="situation",
            needs_retrieval=True,
            extracted_query=intent.extracted_query or segment,
            events=[compact],
        )
    if intent.kind == SegmentIntentKind.CHECKLIST and intent.checklist:
        status = intent.checklist.status
        if status in {"done", "finished", "completed"}:
            status = "complete"
        elif segment_reports_completion(segment):
            status = "complete"
        return LoggerOutput(
            mode=state.mode.value,
            step_update={"step": intent.checklist.step_label, "status": status, "id": intent.checklist.step_id},
            events=[compact],
            needs_retrieval=False,
        )
    if intent.kind == SegmentIntentKind.LOG:
        output = LoggerOutput(mode=state.mode.value, events=[compact], needs_retrieval=False)
        if intent.checklist and intent.checklist.confidence >= INFERENCE_CONFIDENCE_THRESHOLD:
            status = intent.checklist.status
            if status in {"done", "finished", "completed"}:
                status = "complete"
            elif status in {"inprogress", "started", "active"}:
                status = "in_progress"
            if segment_reports_checklist_progress(segment) or status in {"complete", "in_progress"}:
                output.step_update = {
                    "id": intent.checklist.step_id,
                    "step": intent.checklist.step_label,
                    "status": status,
                }
        return output
    return None


def _reconcile_logger_output(
    output: LoggerOutput,
    intent: SegmentIntent,
    checklist: ChecklistState,
    segment: str,
) -> LoggerOutput:
    """Intent wins over LLM when the classifier is confident."""
    if intent.kind == SegmentIntentKind.QUESTION and intent.confidence >= 0.7:
        output.mode = "query"
        output.needs_retrieval = True
        output.extracted_query = intent.extracted_query or segment
        if intent.checklist and intent.checklist.confidence >= 0.72:
            output.step_update = {
                "step": intent.checklist.step_label,
                "status": intent.checklist.status,
            }
        return output
    if intent.kind == SegmentIntentKind.CHECKLIST and intent.checklist:
        output.mode = state_mode_or_logging(output.mode)
        output.needs_retrieval = False
        status = intent.checklist.status
        if status in {"done", "finished", "completed"} or segment_reports_completion(segment):
            status = "complete"
        output.step_update = {"step": intent.checklist.step_label, "status": status, "id": intent.checklist.step_id}
        return output
    if intent.kind == SegmentIntentKind.LOG and intent.confidence >= 0.65:
        output.needs_retrieval = False
        if output.mode == "query":
            output.mode = state_mode_or_logging(output.mode)
        if intent.checklist and intent.checklist.confidence >= INFERENCE_CONFIDENCE_THRESHOLD:
            output.step_update = {
                "step": intent.checklist.step_label,
                "status": intent.checklist.status,
            }
        return output
    return _apply_high_confidence_inference(output, checklist, segment, intent=intent)


def state_mode_or_logging(mode: str) -> str:
    return mode if mode in {"logging", "situation"} else "logging"


def _finalize_retrieval_flags(
    output: LoggerOutput,
    intent: SegmentIntent,
    segment: str,
) -> LoggerOutput:
    """Only run KB search for clear questions or active situations — not every LLM query flag."""
    if not output.needs_retrieval:
        return output
    if intent.kind == SegmentIntentKind.SITUATION:
        return output
    if intent.kind == SegmentIntentKind.QUESTION and intent.is_question:
        return output
    if intent.kind == SegmentIntentKind.QUESTION and intent.confidence >= 0.65:
        return output
    query = (output.extracted_query or segment).strip()
    if is_explicit_question(query):
        return output
    output.needs_retrieval = False
    if output.mode == "query":
        output.mode = state_mode_or_logging(output.mode)
    return output


import logging as _logging

_logger = _logging.getLogger(__name__)


async def _gate_checklist_update(
    output: LoggerOutput,
    checklist: ChecklistState,
    segment: str,
    intent: SegmentIntent,
) -> LoggerOutput:
    """Confirm checklist marks — trust clear completion speech; LLM only for ambiguous cases."""
    hint = intent.checklist or infer_step_update_scored(checklist, segment)
    if not output.step_update and not hint:
        return output

    def _apply_hint(h: StepInference) -> None:
        status = h.status
        if status in {"done", "finished", "completed"}:
            status = "complete"
        output.step_update = {"id": h.step_id, "step": h.step_label, "status": status}
        output.needs_retrieval = False
        if output.mode == "query":
            output.mode = state_mode_or_logging(output.mode)

    def _step_update_matches_hint() -> bool:
        if not output.step_update or not hint:
            return False
        step_name = str(output.step_update.get("step", "")).strip().lower()
        step_id = str(output.step_update.get("id", "")).strip()
        return step_name == hint.step_label.lower() or step_id == hint.step_id

    if intent.kind == SegmentIntentKind.CHECKLIST and hint and hint.confidence >= INFERENCE_CONFIDENCE_THRESHOLD:
        _apply_hint(hint)
        return output

    if hint and segment_reports_checklist_progress(segment):
        if hint.confidence >= INFERENCE_CONFIDENCE_THRESHOLD:
            _apply_hint(hint)
            return output

    if _step_update_matches_hint() and hint and hint.confidence >= INFERENCE_CONFIDENCE_THRESHOLD:
        return output

    if os.environ.get("VOICE_CHECKLIST_LLM", "1").strip().lower() in {"0", "false", "no"}:
        if hint:
            _apply_hint(hint)
        return output

    decision = await asyncio.to_thread(
        assess_checklist_mark,
        segment,
        checklist,
        hint=hint,
    )
    if decision.should_mark and decision.step_id:
        status = decision.status or (hint.status if hint else "in_progress")
        if segment_reports_completion(segment) and status not in {"completed", "complete", "done", "finished"}:
            status = "completed"
        if status in {"done", "finished", "completed"}:
            status = "complete"
        output.step_update = {
            "id": decision.step_id,
            "step": decision.step_label,
            "status": status,
        }
        output.needs_retrieval = False
        if output.mode == "query":
            output.mode = state_mode_or_logging(output.mode)
        return output

    if (
        decision.reason == "llm_parse_failed"
        and hint
        and hint.confidence >= INFERENCE_CONFIDENCE_THRESHOLD
        and (
            segment_reports_checklist_progress(segment)
            or intent.kind == SegmentIntentKind.CHECKLIST
        )
    ):
        _apply_hint(hint)
        return output

    if hint and hint.confidence >= 0.65 and segment_reports_checklist_progress(segment):
        _apply_hint(hint)
        return output

    if _step_update_matches_hint() and segment_reports_checklist_progress(segment):
        return output

    output.step_update = None
    return output


async def run_logger(
    *,
    state: SessionState,
    checklist: ChecklistState,
    segment: str,
    context_block: str = "",
) -> LoggerOutput:
    _logger.debug("run_logger called: segment=%s, mode=%s", segment[:50], state.mode.value)
    dialogue_context = format_dialogue_transcript(state.dialogue[:-1], max_turns=12, max_chars=2000)
    intent = await asyncio.to_thread(
        classify_intent_for_utterance,
        segment,
        checklist,
        current_mode=state.mode.value,
        dialogue_context=dialogue_context,
    )
    _logger.debug("intent classified: kind=%s, confidence=%.2f", intent.kind.value, intent.confidence)

    fast = _logger_output_from_intent(intent, segment, state=state)
    if fast:
        output = _reconcile_logger_output(fast, intent, checklist, segment)
    else:
        output = _heuristic_logger(state, segment, checklist, intent=intent)
        output = _reconcile_logger_output(output, intent, checklist, segment)
    output = await _gate_checklist_update(output, checklist, segment, intent)
    return _finalize_retrieval_flags(output, intent, segment)


def _parse_logger_json(raw: str) -> LoggerOutput | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return LoggerOutput(
        mode=str(data.get("mode", "logging")),
        situation_resolved=bool(data.get("situation_resolved", False)),
        phase=str(data.get("phase", "")),
        step_update=data.get("step_update"),
        events=[str(e) for e in data.get("events", [])] if data.get("events") else [],
        extracted_query=data.get("extracted_query"),
        needs_retrieval=bool(data.get("needs_retrieval", False)),
    )


def _heuristic_logger(
    state: SessionState,
    segment: str,
    checklist: ChecklistState | None = None,
    *,
    intent: SegmentIntent | None = None,
) -> LoggerOutput:
    if intent:
        fast = _logger_output_from_intent(intent, segment, state=state)
        if fast and intent.kind != SegmentIntentKind.AMBIGUOUS:
            return fast
    text = segment.lower()
    if checklist is not None:
        scored = infer_step_update_scored(checklist, segment)
        if scored and scored.confidence >= INFERENCE_CONFIDENCE_THRESHOLD:
            return LoggerOutput(
                mode=state.mode.value,
                step_update={"step": scored.step_label, "status": scored.status},
                events=[_compact_text(segment)],
            )
        inferred = infer_step_update_from_transcript(checklist, segment)
        if inferred:
            return LoggerOutput(
                mode=state.mode.value,
                step_update=inferred,
                events=[_compact_text(segment)],
            )
    if state.mode == OperationMode.SITUATION and _matches_any(text, RESOLVED_PATTERNS):
        return LoggerOutput(mode="logging", situation_resolved=True, events=[_compact_text(segment)])
    if _matches_any(text, COMPLICATION_PATTERNS):
        return LoggerOutput(
            mode="situation",
            needs_retrieval=True,
            extracted_query=segment,
            events=[_compact_text(segment)],
        )
    if is_explicit_question(segment):
        return LoggerOutput(
            mode="query",
            needs_retrieval=True,
            extracted_query=segment,
            events=[_compact_text(segment)],
        )
    return LoggerOutput(mode=state.mode.value, events=[_compact_text(segment)])


def apply_logger_output(state: SessionState, output: LoggerOutput, checklist: ChecklistState) -> OperationMode:
    if output.phase:
        state.phase = output.phase
    for event in output.events or []:
        if event.strip():
            state.append_event("event", event.strip())

    if output.step_update and isinstance(output.step_update, dict):
        step_name = str(output.step_update.get("step", ""))
        status = str(output.step_update.get("status", "")).lower()
        if status in {"done", "finished"}:
            status = "complete"
        elif status in {"inprogress", "started", "active"}:
            status = "in_progress"
        step_id: str | None = None
        raw_id = output.step_update.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            hint = raw_id.strip()
            if any(step.id == hint for step in checklist.steps):
                step_id = hint
            else:
                step_id = checklist.resolve_step_id(hint)
        if not step_id and step_name.strip():
            step_id = checklist.resolve_step_id(step_name)
        if step_id and status in {"completed", "complete"}:
            checklist.apply_step_update(step_id, "complete")
            state.append_event("step", f"completed: {step_name}")
        elif step_id and status == "in_progress":
            checklist.apply_step_update(step_id, "in_progress")
            state.append_event("step", f"in progress: {step_name}")

    if output.situation_resolved and state.mode == OperationMode.SITUATION:
        state.active_situation = None
        state.mode = OperationMode.LOGGING
        state.append_event("resolution", "situation resolved")
        return OperationMode.LOGGING

    new_mode = output.mode if output.mode in {"logging", "situation", "query"} else state.mode.value
    if new_mode == "situation" and state.mode != OperationMode.SITUATION:
        state.active_situation = ActiveSituation(
            summary=output.extracted_query or (output.events[0] if output.events else "complication"),
            opened_at=time.time(),
        )
        state.append_event("situation", state.active_situation.summary)
    if new_mode == "query":
        state.append_event("query", output.extracted_query or "")

    state.mode = OperationMode(new_mode)
    return state.mode


def format_candidates(snippets: list[Snippet]) -> str:
    lines = []
    for snip in snippets:
        chunk_id = snip.chunk_id or snip.source
        lines.append(f"{chunk_id} | {snip.source} | {snip.doc_type} | {snip.date} | {snip.text[:500]}")
    return "\n".join(lines)


def parse_grounded_response(raw: str) -> AnswerResult:
    match = _GROUNDED_RE.search(raw.strip())
    if not match:
        return AnswerResult(grounded_ids=[], spoken_text=raw.strip(), refusal=True)
    grounded_raw = match.group(1).strip()
    remainder = _GROUNDED_RE.sub("", raw, count=1).strip()
    if grounded_raw.upper() == "NONE":
        spoken = remainder or "I found related material but nothing that directly answers your question."
        return AnswerResult(grounded_ids=[], spoken_text=clamp_spoken_text(spoken), refusal=True)
    ids = [part.strip() for part in re.findall(r"\[([^\]]+)\]", grounded_raw)]
    if not ids:
        ids = [grounded_raw.strip("[] \"'")]
    spoken = remainder or "See the cited source on screen."
    return AnswerResult(grounded_ids=ids, spoken_text=clamp_spoken_text(spoken))


async def run_answer(query: str, candidates: list[Snippet], *, live_context: str = "") -> AnswerResult:
    prompt = build_answer_prompt(
        situation_or_query=query,
        moss_candidates=format_candidates(candidates),
        live_context=live_context,
    )
    raw = await asyncio.to_thread(converse_text, prompt, max_tokens=120, temperature=0.2)
    if not raw:
        return AnswerResult(grounded_ids=[], spoken_text="", refusal=True)
    return parse_grounded_response(raw)


async def run_nova_fallback_answer(
    query: str,
    *,
    live_context: str = "",
    procedure: str = "",
    hints: list[Snippet] | None = None,
) -> AnswerResult:
    """Nova answer from live case context when indexed KB search has no grounded hit."""
    prompt = build_nova_fallback_prompt(
        query=query,
        live_context=live_context,
        procedure=procedure,
        local_hints=format_candidates(hints[:4]) if hints else "",
    )
    model = resolve_model("answer")
    raw = await asyncio.to_thread(converse_text, prompt, model=model, max_tokens=120, temperature=0.2)
    if not raw:
        return AnswerResult(grounded_ids=[], spoken_text="", refusal=True)
    text = raw.strip()
    if text.upper().startswith("MISSING:"):
        spoken = clamp_spoken_text(text.split(":", 1)[-1])
        return AnswerResult(grounded_ids=[], spoken_text=spoken, refusal=True)
    spoken = clamp_spoken_text(text)
    if not spoken:
        return AnswerResult(grounded_ids=[], spoken_text="", refusal=True)
    return AnswerResult(grounded_ids=["nova-context"], spoken_text=spoken, refusal=False)


def build_deterministic_summary(
    *,
    patient_id: str,
    procedure: str,
    checklist: dict,
    events: list[dict],
    complications: list[dict],
    transcript: list[dict] | None = None,
    patient_context: str = "",
    manual_notes: str = "",
    comorbidities: list[str] | None = None,
) -> str:
    steps = checklist.get("steps", [])
    step_lines = [
        f"- {s.get('label', s.get('id'))}: {s.get('status', 'pending')}" for s in steps
    ] or ["- Not recorded"]

    timeline = [
        f"- {_format_ts(float(e.get('ts', 0)))} [{e.get('type', 'event')}] {e.get('text', '')}"
        for e in sorted(events, key=lambda item: float(item.get("ts", 0)))
    ] or ["- Not recorded"]

    dialogue_lines = _format_transcript_lines(transcript or [])
    if not dialogue_lines:
        dialogue_lines = ["- Not recorded"]

    chart_lines: list[str] = []
    if patient_context.strip():
        chart_lines.append(patient_context.strip())
    if comorbidities:
        chart_lines.append(f"- Comorbidities: {', '.join(comorbidities)}")
    if manual_notes.strip():
        chart_lines.append(f"- Prep notes: {manual_notes.strip()}")
    chart_body = "\n".join(chart_lines) if chart_lines else "- Not recorded"

    if complications:
        comp_lines = [
            f"- {item.get('description', 'complication')} ({'resolved' if item.get('resolved') else 'open'})"
            for item in complications
        ]
    else:
        situation_events = [e for e in events if e.get("type") in {"situation", "resolution"}]
        comp_lines = [
            f"- {_format_ts(float(e.get('ts', 0)))} {e.get('text', '')}" for e in situation_events
        ] or ["- Not recorded"]

    query_events = [e for e in events if e.get("type") == "query"]
    query_lines = [
        f"- {_format_ts(float(e.get('ts', 0)))} {e.get('text', '')}" for e in query_events
    ] or ["- Not recorded"]

    pending_steps = [
        s.get("label", s.get("id", "step"))
        for s in steps
        if s.get("status") not in {"completed", "complete"}
    ]
    follow_up = [f"- Pending checklist step: {label}" for label in pending_steps] or ["- Not recorded"]

    sections = [
        ("Procedure", f"{procedure} — patient {patient_id}"),
        ("Patient Chart Highlights", chart_body),
        ("Intraoperative Dialogue", "\n".join(f"- {line}" if not line.startswith("-") else line for line in dialogue_lines)),
        ("Steps Completed", "\n".join(step_lines)),
        ("Timeline", "\n".join(timeline)),
        ("Complications & Resolutions", "\n".join(comp_lines)),
        ("Queries Answered", "\n".join(query_lines)),
        ("Items to Verify / Follow-up", "\n".join(follow_up)),
    ]
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections)


async def run_summary(
    *,
    patient_id: str,
    procedure: str,
    checklist: dict,
    events: list[dict],
    complications: list[dict],
    mode_transitions: list[dict] | None = None,
    transcript: list[dict] | None = None,
    patient_context: str = "",
    manual_notes: str = "",
    comorbidities: list[str] | None = None,
) -> str:
    transcript_rows = normalize_transcript_turns(transcript or [])
    payload = {
        "patient_id": patient_id,
        "procedure": procedure,
        "patient_context": patient_context,
        "manual_notes": manual_notes,
        "comorbidities": comorbidities or [],
        "checklist": checklist,
        "events": events,
        "complications": complications,
        "mode_transitions": mode_transitions or [],
        "transcript": transcript_rows,
        "transcript_formatted": _format_transcript_lines(transcript_rows),
    }
    prompt = build_summary_prompt(session_log_json=json.dumps(payload, indent=2))
    model = resolve_model("summary")
    raw = await asyncio.to_thread(
        converse_text,
        prompt,
        model=model,
        max_tokens=2200,
        temperature=0.1,
    )
    if raw:
        normalized = normalize_summary_markdown(raw)
        if _summary_has_required_sections(normalized):
            return normalized
    return build_deterministic_summary(
        patient_id=patient_id,
        procedure=procedure,
        checklist=checklist,
        events=events,
        complications=complications,
        transcript=transcript,
        patient_context=patient_context,
        manual_notes=manual_notes,
        comorbidities=comorbidities,
    )


def build_session_context_block(summary: str, state: SessionState, *, phase: str = "", active_step: str = "") -> str:
    recent = state.compacted_events()[-12:]
    log_block = "\n".join(f"- [{e.type}] {e.text}" for e in recent)
    dialogue_block = format_dialogue_transcript(state.dialogue)
    parts = [f"Patient context:\n{summary}"]
    if phase:
        parts.append(f"Phase: {phase}")
    if active_step:
        parts.append(f"Active step: {active_step}")
    if dialogue_block:
        parts.append(f"OR dialogue (full session, most recent last):\n{dialogue_block}")
    if log_block:
        parts.append(f"Recent log:\n{log_block}")
    return "\n\n".join(parts)


def format_dialogue_transcript(
    turns: list[DialogueTurn],
    *,
    max_turns: int = 32,
    max_chars: int = 6000,
) -> str:
    if not turns:
        return ""
    recent = turns[-max_turns:]
    lines: list[str] = []
    for turn in recent:
        label = "Surgeon" if turn.role == "surgeon" else "Scalpel"
        lines.append(f"{label}: {turn.text}")
    block = "\n".join(lines)
    if len(block) <= max_chars:
        return block
    trimmed = block[-max_chars:]
    if "\n" in trimmed:
        trimmed = trimmed.split("\n", 1)[-1]
    return trimmed.strip()


def expand_retrieval_query(state: SessionState, query: str, segment: str) -> str:
    """Include prior OR dialogue in retrieval so multi-turn questions search well."""
    if len(state.dialogue) < 2:
        return query
    prior = state.dialogue[:-1]
    dialogue_tail = format_dialogue_transcript(prior, max_turns=12, max_chars=1500)
    if not dialogue_tail:
        return query
    return f"{query.strip()}\n\nPrior OR dialogue:\n{dialogue_tail}"
