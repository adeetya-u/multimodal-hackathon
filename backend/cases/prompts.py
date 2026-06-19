from __future__ import annotations

import json

from .checklist import ChecklistState, StepInference
from .bootstrap import SurgeryContext


def build_logger_router_prompt(
    *,
    current_mode: str,
    step_checklist: ChecklistState,
    segment: str,
    context_block: str = "",
    checklist_hint: StepInference | None = None,
) -> str:
    steps = [{"step": s.label, "status": s.status, "id": s.id, "aliases": s.aliases[:4]} for s in step_checklist.steps]
    hint_block = ""
    if checklist_hint:
        hint_block = (
            f"\nFUZZY CHECKLIST MATCH: {checklist_hint.step_label} → {checklist_hint.status} "
            f"(confidence {checklist_hint.confidence:.2f}). Prefer this unless the utterance is clearly a question.\n"
        )
    return f"""You are the silent scribe and router for an active surgical procedure.
Output JSON only — never speak, never give clinical advice.

Treat each SEGMENT using the OR DIALOGUE in CASE CONTEXT when the surgeon uses pronouns or follow-ups
(also, that, what about, same for, her/his/the dose). Rewrite extracted_query as a standalone question that
preserves necessary context from the dialogue. Otherwise classify the segment on its own merits.

CURRENT MODE: {current_mode}
STEP CHECKLIST: {json.dumps(steps)}
CASE CONTEXT (patient chart, OR dialogue, recent log):
{context_block or "(none)"}{hint_block}
SEGMENT: {segment}

Classify intent:
- question: asks for information (what/how/should/is there/any allergies) → needs_retrieval=true, mode=query
- log: declarative status note with no question → mode=logging, needs_retrieval=false
- checklist: marks progress on a step (done/starting/complete/step N) → step_update set, needs_retrieval=false
- situation: active complication needing guidance → mode=situation, needs_retrieval=true

Output ONLY:
{{
  "mode": "logging | situation | query",
  "situation_resolved": true | false,
  "phase": "<current phase>",
  "step_update": {{ "step": "<name>", "status": "in_progress | completed" }} | null,
  "events": ["<terse note>", ...],
  "extracted_query": "<plain question>" | null,
  "needs_retrieval": true | false
}}

Checklist rules: forward-only — never go backward. Surgeons may skip ahead (e.g. "skip to
incision", "starting femoral cut", "trials look good", "step 5 complete", "mark step 3 done").
When a later step is started or completed, emit step_update for that step and assume all earlier pending steps are complete.
Match step names, ids, step numbers (1-based), or aliases from STEP CHECKLIST — each case has its own labels.
Phrases like "done with X", "finished X", "check step N" imply completion even without exact wording.
When speech does not match literally, infer the closest checklist step from context and aliases.
"""


def build_answer_prompt(*, situation_or_query: str, moss_candidates: str, live_context: str = "") -> str:
    live_section = f"\nLIVE CASE CONTEXT:\n{live_context.strip()}\n" if live_context.strip() else ""
    return f"""Voice assistant in an operating theatre. Address the question using ONLY verified excerpts.
Use the OR dialogue in LIVE CASE CONTEXT to resolve follow-ups, pronouns, and elliptical questions.
Never state the patient has no allergies or NKDA unless an excerpt explicitly documents that.
If chart context documents penicillin or other allergy, never contradict it.
{live_section}
If no excerpt answers the question, output:
  GROUNDED: NONE
then one spoken sentence explaining what is missing.

Otherwise:
  GROUNDED: [<chunk_id>]
then 1-2 spoken lines maximum. Medically succinct — doses, thresholds, or actions only; no preamble.

QUESTION:
{situation_or_query}

CANDIDATES (chunk_id | SOURCE | TYPE | DATE | text):
{moss_candidates}
"""


def build_intro_answer_prompt(*, question: str, reference_excerpts: str) -> str:
    return f"""Voice assistant on a public knee surgery education demo. No patient chart — general reference only.
Answer using ONLY the reference excerpts below.

Rules:
- Reply in ONE short spoken sentence (max ~22 words). Use a second sentence only if absolutely necessary.
- Never preamble, never "I'm here to walk you through", never bullet lists.
- Plain speech for TTS only.

If no excerpt answers the question, output:
  GROUNDED: NONE
then one short sentence of general guidance.

Otherwise:
  GROUNDED: [<chunk_id>]
then your one (or at most two) short spoken sentences.

QUESTION:
{question}

REFERENCE EXCERPTS (chunk_id | SOURCE | TYPE | text):
{reference_excerpts}
"""


def build_external_answer_prompt(*, query: str, live_context: str = "", procedure: str = "") -> str:
    live_section = f"\nLIVE CASE CONTEXT:\n{live_context.strip()}\n" if live_context.strip() else ""
    procedure_line = f"PROCEDURE: {procedure}\n" if procedure.strip() else ""
    return f"""Scalpel voice assistant in the OR. Local patient chart and SOP search returned no relevant excerpts.
{procedure_line}{live_section}
Call external_web_search exactly once with a focused clinical query, then answer the surgeon.

Rules:
- Reply with 1-2 spoken lines maximum after you receive search results.
- Medically succinct: state dose, threshold, or action; no preamble, disclaimers, or bullet lists.
- Plain speech for TTS only.
- If results are inconclusive, one line stating what is missing.

QUESTION:
{query}
"""


def build_nova_fallback_prompt(
    *,
    query: str,
    live_context: str = "",
    procedure: str = "",
    local_hints: str = "",
) -> str:
    live_section = f"\nLIVE CASE CONTEXT:\n{live_context.strip()}\n" if live_context.strip() else ""
    procedure_line = f"PROCEDURE: {procedure}\n" if procedure.strip() else ""
    hints_section = ""
    if local_hints.strip():
        hints_section = f"\nLOCAL HINTS (tangential excerpts — use only if relevant):\n{local_hints.strip()}\n"
    return f"""Scalpel voice assistant in the OR. Indexed chart/SOP search found no direct excerpt for this question.
Answer using ONLY the live case context and local hints below.
Use the OR dialogue in LIVE CASE CONTEXT to resolve follow-ups and pronouns.
Never invent allergies or claim NKDA unless explicitly in the context above.
If LIVE CASE CONTEXT lists medications, allergies, labs, or other facts, state them — do not reply MISSING.
{procedure_line}{live_section}{hints_section}
Rules:
- Reply with 1-2 short spoken lines for TTS. Plain speech only — no markdown or bullet lists.
- Use only facts present in the context above. Do not invent patient details, doses, or outcomes.
- If the context truly cannot answer, reply exactly: MISSING: <one short sentence stating what is absent>.

QUESTION:
{query}
"""


def build_summary_prompt(*, session_log_json: str) -> str:
    return f"""You are a surgical documentation assistant. Write a polished post-operative summary in markdown.

Use EXACTLY these section headings (## Title), in this order:
## Procedure
## Patient Chart Highlights
## Intraoperative Dialogue
## Steps Completed
## Timeline
## Complications & Resolutions
## Queries Answered
## Items to Verify / Follow-up

Rules:
- Use only facts from the session payload (patient chart, OR transcript, checklist, events).
- Do not invent clinical details, doses, or outcomes not present in the data.
- Write in clear clinical prose suitable for a surgeon's handoff note.
- Use bullet lists (- item) under each section where appropriate.
- Patient Chart Highlights: distill relevant prep/chart context (allergies, comorbidities, key history).
- Intraoperative Dialogue: summarize surgeon–agent conversation themes; do not quote every line verbatim.
- Timeline: chronological bullets with HH:MM:SS when timestamps are available.
- If a section has no data, write "Not recorded" as a single bullet.

SESSION PAYLOAD (JSON):
{session_log_json}
"""


def build_logger_instructions(checklist: ChecklistState, context: SurgeryContext) -> str:
    steps = ", ".join(s.label for s in checklist.steps[:8])
    return (
        f"You are Scalpel, a surgical logging assistant for {context.procedure}. "
        f"Patient {context.patient_id}. Checklist milestones: {steps}. "
        "Listen and log; answer questions when asked."
    )
