"""Nebius/LLM gate — decide if surgeon speech should mark the OR checklist."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from .checklist import (
    ChecklistState,
    ChecklistStep,
    StepInference,
    infer_step_update_scored,
    segment_reports_completion,
)
from .llm import converse_text, resolve_model

logger = logging.getLogger(__name__)


@dataclass
class ChecklistMarkDecision:
    should_mark: bool
    step_id: str | None = None
    step_label: str | None = None
    status: str | None = None
    confidence: float = 0.0
    reason: str = ""


def _strip_llm_noise(text: str) -> str:
    from .case_intake_extract import _strip_llm_noise as strip

    return strip(text)


def _parse_decision_json(text: str) -> dict | None:
    cleaned = _strip_llm_noise(text)
    for candidate in (cleaned, text.strip()):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start < 0 or end <= start:
                continue
            try:
                data = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            return data
    return None


def _ordered_steps_for_review(checklist: ChecklistState) -> list[ChecklistStep]:
    """Current / next incomplete first, then later pending steps one by one."""
    indices: list[int] = []
    in_progress = checklist.current_in_progress_index()
    if in_progress is not None:
        indices.append(in_progress)
    forward = checklist.forward_min_index()
    if forward < len(checklist.steps) and forward not in indices:
        indices.append(forward)
    for index, step in enumerate(checklist.steps):
        if step.status != "complete" and index not in indices:
            indices.append(index)
    return [checklist.steps[i] for i in indices]


def _build_step_prompt(
    segment: str,
    checklist: ChecklistState,
    step: ChecklistStep,
    *,
    step_index: int,
    hint: StepInference | None = None,
) -> str:
    hint_line = ""
    if hint and hint.step_id == step.id:
        hint_line = (
            f"\nHeuristic note: fuzzy match suggested this step ({hint.status}, "
            f"confidence {hint.confidence:.2f}) — verify independently.\n"
        )
    return f"""You gate OR checklist updates from surgeon speech.
Evaluate ONLY the single step below — do not consider other checklist items yet.

Procedure: {checklist.procedure}
Step #{step_index + 1} under review:
  id: {step.id}
  label: {step.label}
  status: {step.status}
  aliases: {json.dumps((step.aliases or [])[:4], ensure_ascii=False)}

Utterance: {segment!r}
{hint_line}
Return ONLY JSON:
{{
  "mark_checklist": true | false,
  "status": "in_progress" | "completed" | null,
  "confidence": 0.0-1.0,
  "reason": "<short>"
}}

Mark true ONLY if this utterance clearly starts or completes THIS step.

Mark false when:
- the utterance is a clinical question (including short prompts like "patient's allergies")
- the surgeon reports progress on a different milestone
- casual mention with no progress ("we'll verify allergies later")
- general patient facts with no checklist progress on this step
"""


def _status_from_llm(raw: str | None) -> str | None:
    if not raw:
        return None
    status = str(raw).strip().lower()
    if status in {"done", "finished", "complete", "completed"}:
        return "completed"
    if status in {"in_progress", "inprogress", "started", "starting", "active"}:
        return "in_progress"
    return None


def _assess_single_step(
    segment: str,
    checklist: ChecklistState,
    step: ChecklistStep,
    *,
    step_index: int,
    hint: StepInference | None,
    model: str,
) -> ChecklistMarkDecision:
    prompt = _build_step_prompt(
        segment,
        checklist,
        step,
        step_index=step_index,
        hint=hint if hint and hint.step_id == step.id else None,
    )
    raw = converse_text(prompt, model=model, max_tokens=180, temperature=0.0)
    parsed = _parse_decision_json(raw or "")
    if not parsed:
        return ChecklistMarkDecision(should_mark=False, reason="llm_parse_failed")

    should_mark = bool(parsed.get("mark_checklist"))
    confidence = float(parsed.get("confidence") or 0.0)
    reason = str(parsed.get("reason") or "").strip()
    status = _status_from_llm(parsed.get("status"))

    if should_mark:
        default_status = "in_progress"
        if segment_reports_completion(segment):
            default_status = "completed"
        elif hint and hint.step_id == step.id and hint.status:
            default_status = hint.status
        return ChecklistMarkDecision(
            should_mark=True,
            step_id=step.id,
            step_label=step.label,
            status=status or default_status,
            confidence=confidence,
            reason=reason or "llm_approved",
        )
    return ChecklistMarkDecision(should_mark=False, confidence=confidence, reason=reason or "step_rejected")


def assess_checklist_mark(
    segment: str,
    checklist: ChecklistState,
    *,
    hint: StepInference | None = None,
) -> ChecklistMarkDecision:
    """Walk checklist steps in order — current step first, then later steps one by one."""
    if os.environ.get("VOICE_CHECKLIST_LLM", "1").strip().lower() in {"0", "false", "no"}:
        if hint:
            return ChecklistMarkDecision(
                should_mark=True,
                step_id=hint.step_id,
                step_label=hint.step_label,
                status=hint.status,
                confidence=hint.confidence,
                reason="llm_gate_disabled",
            )
        return ChecklistMarkDecision(should_mark=False, reason="llm_gate_disabled")

    if not checklist.steps or not segment.strip():
        return ChecklistMarkDecision(should_mark=False, reason="empty_input")

    hint = hint or infer_step_update_scored(checklist, segment)
    model = resolve_model("checklist") or resolve_model("intent") or resolve_model("logger")
    max_steps = int(os.environ.get("CHECKLIST_LLM_MAX_STEPS", "6"))

    steps = _ordered_steps_for_review(checklist)[:max_steps]
    for step in steps:
        step_index = checklist.step_index(step.id)
        decision = _assess_single_step(
            segment,
            checklist,
            step,
            step_index=step_index,
            hint=hint,
            model=model,
        )
        if decision.should_mark:
            logger.info(
                "checklist LLM matched step %s (%s): %s",
                step.id,
                step.label,
                decision.reason,
            )
            return decision

    return ChecklistMarkDecision(should_mark=False, reason="no_step_matched_sequential")
