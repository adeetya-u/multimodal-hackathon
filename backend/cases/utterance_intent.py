"""Fast intent classification for OR voice — question vs log vs checklist update."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum

from .llm import converse_text, resolve_model
from .checklist import ChecklistState, StepInference, infer_step_update_scored, segment_reports_checklist_progress
from .mode_controller import COMPLICATION_PATTERNS, _matches_any

_QUESTION_START_RE = re.compile(
    r"^(?:what|how|when|where|why|which|who|can|could|should|would|is|are|was|were|"
    r"do|does|did|have|has|had|any|tell me|remind me|give me)\b",
    re.IGNORECASE,
)

_QUESTION_INLINE_RE = re.compile(
    r"\b(?:what(?:'s| is)|how (?:do|should|long|much)|is there|are there|should (?:we|i)|"
    r"can (?:we|i)|does (?:the )?patient|did (?:we|i)|have (?:we|i)|"
    r"any (?:allerg|contraind|issue|problem))\b",
    re.IGNORECASE,
)

_FOLLOW_UP_RE = re.compile(
    r"\b(?:also|and what about|what about|how about|same for|that one|for that|"
    r"follow(?:ing)? up on|regarding that|the dose|renal dosing|her dose|his dose)\b",
    re.IGNORECASE,
)


def is_follow_up_utterance(segment: str) -> bool:
    return bool(_FOLLOW_UP_RE.search(segment.strip()))

_LOG_STATEMENT_RE = [
    r"\b(?:done|finished|complete|completed|checked off|verified|confirmed|given|administered)\b",
    r"\b(?:starting|beginning|moving to|proceeding to|now (?:on|doing|at))\b",
    r"\b(?:no known allergies|nkda|no allergies)\b",
    r"\b(?:timeout (?:is )?(?:done|complete)|prep(?:ped|ping)? (?:is )?(?:done|complete))\b",
    r"\b(?:log(?:ged)?|noted|recording)\b",
]

_CHECKLIST_ACTION_RE = [
    r"\b(?:mark|check|complete|finish|done with|skip(?:ping)? to|move(?:d)? to)\b",
    r"\b(?:step|number|#)\s*\d+\b",
]


class SegmentIntentKind(str, Enum):
    QUESTION = "question"
    LOG = "log"
    CHECKLIST = "checklist"
    SITUATION = "situation"
    AMBIGUOUS = "ambiguous"


@dataclass
class SegmentIntent:
    kind: SegmentIntentKind
    confidence: float
    is_question: bool = False
    is_log: bool = False
    is_checklist: bool = False
    is_situation: bool = False
    extracted_query: str | None = None
    checklist: StepInference | None = None
    follow_up_cue: bool = False

    @property
    def needs_retrieval(self) -> bool:
        return self.is_question or self.is_situation


def _looks_like_question(segment: str) -> bool:
    text = segment.strip()
    if not text:
        return False
    if "?" in text:
        return True
    lower = text.lower()
    if _QUESTION_START_RE.search(lower):
        return True
    if _QUESTION_INLINE_RE.search(lower):
        return True
    return False


def is_explicit_question(segment: str) -> bool:
    """Strong question signal — used before verbalizing a KB miss."""
    text = segment.strip()
    if not text:
        return False
    if "?" in text:
        return True
    return bool(_QUESTION_START_RE.search(text.lower()))


def _looks_like_log_statement(segment: str, *, checklist: StepInference | None) -> bool:
    text = segment.strip().lower()
    if not text or _looks_like_question(segment):
        return False
    if checklist and checklist.confidence >= 0.72 and segment_reports_checklist_progress(segment):
        return True
    if _matches_any(text, _CHECKLIST_ACTION_RE):
        return True
    return _matches_any(text, _LOG_STATEMENT_RE)


def _looks_like_situation(segment: str) -> bool:
    return _matches_any(segment.lower(), COMPLICATION_PATTERNS)


def classify_segment_intent(
    segment: str,
    checklist: ChecklistState,
    *,
    current_mode: str = "logging",
) -> SegmentIntent:
    """Heuristic hint for the LLM — not authoritative when VOICE_INTENT_LLM is on."""
    normalized = segment.strip()
    if not normalized:
        return SegmentIntent(kind=SegmentIntentKind.AMBIGUOUS, confidence=0.0)

    scored = infer_step_update_scored(checklist, normalized)
    follow_up = bool(_FOLLOW_UP_RE.search(normalized))
    is_question = _looks_like_question(normalized)
    is_situation = _looks_like_situation(normalized)
    reports_progress = segment_reports_checklist_progress(normalized)
    is_checklist = (
        scored is not None
        and scored.confidence >= 0.45
        and not is_question
        and (reports_progress or scored.confidence >= 0.72)
    )
    is_log = _looks_like_log_statement(normalized, checklist=scored)

    if is_situation and not is_question:
        return SegmentIntent(
            kind=SegmentIntentKind.SITUATION,
            confidence=0.85,
            is_situation=True,
            extracted_query=normalized,
            checklist=scored,
            follow_up_cue=follow_up,
        )

    if is_question and not (is_checklist and scored and scored.confidence >= 0.72 and reports_progress):
        return SegmentIntent(
            kind=SegmentIntentKind.QUESTION,
            confidence=0.9 if "?" in normalized else 0.78,
            is_question=True,
            extracted_query=normalized,
            checklist=scored,
            follow_up_cue=follow_up,
        )

    if is_checklist and scored:
        return SegmentIntent(
            kind=SegmentIntentKind.CHECKLIST,
            confidence=scored.confidence,
            is_checklist=True,
            is_log=True,
            checklist=scored,
            follow_up_cue=follow_up,
        )

    if is_log:
        return SegmentIntent(
            kind=SegmentIntentKind.LOG,
            confidence=0.75,
            is_log=True,
            checklist=scored,
            follow_up_cue=follow_up,
        )

    return SegmentIntent(
        kind=SegmentIntentKind.AMBIGUOUS,
        confidence=0.35,
        checklist=scored,
        follow_up_cue=follow_up,
    )


def intent_llm_enabled() -> bool:
    return os.environ.get("VOICE_INTENT_LLM", "1").strip().lower() not in {"0", "false", "no"}


def _coerce_hint_intent(hint: SegmentIntent, segment: str) -> SegmentIntent:
    """When LLM is off or fails, avoid leaving utterances unclassified."""
    if hint.kind != SegmentIntentKind.AMBIGUOUS:
        return hint
    if _looks_like_situation(segment):
        return SegmentIntent(
            kind=SegmentIntentKind.SITUATION,
            confidence=0.6,
            is_situation=True,
            extracted_query=segment,
            checklist=hint.checklist,
        )
    if _looks_like_question(segment):
        return SegmentIntent(
            kind=SegmentIntentKind.QUESTION,
            confidence=0.65,
            is_question=True,
            extracted_query=segment,
            checklist=hint.checklist,
        )
    return SegmentIntent(
        kind=SegmentIntentKind.LOG,
        confidence=0.5,
        is_log=True,
        checklist=hint.checklist,
    )


def _current_step_line(checklist: ChecklistState) -> str:
    in_progress = next((s for s in checklist.steps if s.status == "in_progress"), None)
    if in_progress:
        return f"Active checklist step: {in_progress.label} [{in_progress.status}]"
    first = next((s for s in checklist.steps if s.status != "complete"), None)
    if first:
        return f"Next checklist step: {first.label} [{first.status}]"
    return "Checklist: all steps complete"


def _build_intent_classifier_prompt(
    segment: str,
    checklist: ChecklistState,
    *,
    current_mode: str,
    checklist_hint: StepInference | None,
    dialogue_context: str = "",
) -> str:
    steps = [
        f"{index + 1}. {step.label} [{step.status}]"
        for index, step in enumerate(checklist.steps[:14])
    ]
    hint = ""
    if checklist_hint:
        hint = f"\nFuzzy checklist match: {checklist_hint.step_label} ({checklist_hint.status}, {checklist_hint.confidence:.2f})"
    dialogue_block = ""
    if dialogue_context.strip():
        dialogue_block = f"\nRecent OR dialogue:\n{dialogue_context.strip()}\n"
    current_step = _current_step_line(checklist)
    return f"""Classify ONE surgeon utterance for an OR voice assistant.
Every finalized utterance (after the surgeon pauses) MUST be classified — pick exactly ONE intent.

The SAME words can be a clinical question OR a status/checklist update — decide from wording and context:
- "Patient's allergies." / "Any allergies?" → question (needs chart lookup) when asking for information
- "I verified the patient allergies" / "allergy check done" → checklist (mark allergy step), NOT a question
- "Patient has penicillin allergy noted" → log (status note), not a question

Never output ambiguous. Choose: question | log | checklist | situation.

{current_step}
Checklist:
{chr(10).join(steps) or "(empty)"}
Current mode: {current_mode}{hint}{dialogue_block}
Utterance: {segment}

Output JSON only:
{{"intent":"question|log|checklist|situation","checklist_step":"<exact label or null>","needs_answer":true|false,"confidence":0.0-1.0}}"""


def _parse_intent_json(raw: str) -> dict | None:
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
    return data if isinstance(data, dict) else None


def resolve_intent_with_llm(
    segment: str,
    checklist: ChecklistState,
    *,
    current_mode: str,
    base: SegmentIntent,
    dialogue_context: str = "",
) -> SegmentIntent:
    """Authoritative intent for every finalized utterance when VOICE_INTENT_LLM is on."""
    if not intent_llm_enabled():
        return _coerce_hint_intent(base, segment)

    prompt = _build_intent_classifier_prompt(
        segment,
        checklist,
        current_mode=current_mode,
        checklist_hint=base.checklist,
        dialogue_context=dialogue_context,
    )
    model = resolve_model("intent")
    raw = converse_text(prompt, model=model, max_tokens=160, temperature=0.0)
    parsed = _parse_intent_json(raw or "")
    if not parsed:
        return _coerce_hint_intent(base, segment)

    intent_raw = str(parsed.get("intent", "")).lower()
    needs_answer = bool(parsed.get("needs_answer", False))
    llm_conf = float(parsed.get("confidence") or 0.72)
    step_label = str(parsed.get("checklist_step") or "").strip()
    scored = base.checklist
    if step_label:
        rescored = infer_step_update_scored(checklist, f"{step_label}. {segment}")
        if rescored:
            scored = rescored
        else:
            step_id = checklist.resolve_step_id(step_label)
            if step_id:
                step = next(s for s in checklist.steps if s.id == step_id)
                scored = StepInference(
                    step_id=step.id,
                    step_label=step.label,
                    status="completed",
                    confidence=0.7,
                )

    if intent_raw == "question" or needs_answer:
        return SegmentIntent(
            kind=SegmentIntentKind.QUESTION,
            confidence=llm_conf,
            is_question=True,
            extracted_query=segment,
            checklist=scored,
            follow_up_cue=base.follow_up_cue,
        )
    if intent_raw == "situation":
        return SegmentIntent(
            kind=SegmentIntentKind.SITUATION,
            confidence=llm_conf,
            is_situation=True,
            extracted_query=segment,
            checklist=scored,
            follow_up_cue=base.follow_up_cue,
        )
    if intent_raw == "checklist" and scored:
        return SegmentIntent(
            kind=SegmentIntentKind.CHECKLIST,
            confidence=max(scored.confidence, llm_conf),
            is_checklist=True,
            is_log=True,
            checklist=scored,
            follow_up_cue=base.follow_up_cue,
        )
    if intent_raw == "log":
        return SegmentIntent(
            kind=SegmentIntentKind.LOG,
            confidence=llm_conf,
            is_log=True,
            checklist=scored,
            follow_up_cue=base.follow_up_cue,
        )
    return _coerce_hint_intent(base, segment)


def classify_intent_for_utterance(
    segment: str,
    checklist: ChecklistState,
    *,
    current_mode: str = "logging",
    dialogue_context: str = "",
) -> SegmentIntent:
    """Classify one finalized utterance — LLM when enabled, heuristic fallback otherwise."""
    hint = classify_segment_intent(segment, checklist, current_mode=current_mode)
    if not segment.strip():
        return hint
    return resolve_intent_with_llm(
        segment,
        checklist,
        current_mode=current_mode,
        base=hint,
        dialogue_context=dialogue_context,
    )
