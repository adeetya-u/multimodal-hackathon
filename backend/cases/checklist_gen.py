"""Perioperative milestone checklist generation via AWS Bedrock."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from .llm import converse_text
from .types import CompactPack

logger = logging.getLogger(__name__)

MAX_CHECKLIST_STEPS = 10

DEFAULT_TKA_STEPS = [
    ("timeout", "Surgical timeout and site verification", ["timeout", "time out", "site verification"]),
    ("allergy_abx", "Verify allergies and give antibiotics", ["allergy", "antibiotic", "prophylaxis"]),
    ("position_prep", "Position, prep, and drape", ["positioning", "prep", "drape"]),
    ("approach_exposure", "Surgical approach and exposure", ["approach", "exposure", "arthrotomy"]),
    ("femoral_prep", "Femoral preparation", ["femoral cut", "femur", "distal femur"]),
    ("tibial_prep", "Tibial preparation", ["tibial cut", "tibia", "proximal tibia"]),
    ("trial_balance", "Trialing and ligament balance", ["trial", "balance", "rom"]),
    ("implants", "Cement and place implants", ["cement", "implants", "components"]),
    ("closure", "Closure and dressings", ["closure", "hemostasis", "dressings"]),
    ("pacu_transfer", "Transfer to PACU and handoff", ["pacu", "recovery room", "handoff"]),
]

_MICRO_STEP_PATTERNS = re.compile(
    r"\b(apply tourniquet|tourniquet (up|on|inflated)|make (skin )?incision|skin incision|"
    r"place retractor|pass suture|prepare medial parapatellar)\b",
    re.IGNORECASE,
)


def default_checklist(procedure: str, *, reason: str = "default_tka_fallback") -> dict:
    return {
        "procedure": procedure,
        "mode": "logger",
        "source": reason,
        "steps": [
            {"id": sid, "label": label, "aliases": aliases}
            for sid, label, aliases in DEFAULT_TKA_STEPS
        ],
    }


def _normalize_step(raw: dict, index: int) -> dict | None:
    label = str(raw.get("label", "")).strip()
    if len(label) < 4 or len(label) > 80:
        return None
    if label.startswith("#") or "|" in label or label.lower().startswith("name:"):
        return None
    if _MICRO_STEP_PATTERNS.search(label):
        return None
    step_id = str(raw.get("id") or "").strip()
    if not step_id:
        step_id = re.sub(r"[^a-z0-9]+", "_", label.lower())[:40].strip("_") or f"step_{index}"
    aliases = raw.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []
    aliases = [str(a).strip().lower() for a in aliases if str(a).strip()][:6]
    return {"id": step_id[:48], "label": label.rstrip("."), "aliases": aliases}


def _parse_checklist_json(text: str, procedure: str) -> dict | None:
    from .case_intake_extract import _strip_llm_noise

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
        else:
            if not isinstance(data, dict):
                continue
            steps_raw = data.get("steps")
            if not isinstance(steps_raw, list):
                continue
            steps = [
                s
                for i, raw in enumerate(steps_raw)
                if isinstance(raw, dict) and (s := _normalize_step(raw, i))
            ]
            if len(steps) < 5:
                continue
            return {
                "procedure": str(data.get("procedure") or procedure),
                "mode": "logger",
                "source": "llm",
                "steps": steps[:MAX_CHECKLIST_STEPS],
            }
    return None


def _format_case_intake(case_intake: dict[str, str] | None) -> str:
    if not case_intake:
        return "- None"
    lines = []
    for key, label in (
        ("patient_id", "Patient ID"),
        ("procedure", "Procedure"),
        ("comorbidities", "Comorbidities"),
        ("notes", "Surgeon notes"),
    ):
        value = str(case_intake.get(key, "")).strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines) if lines else "- None"


def _build_prompt(
    procedure: str,
    patient_packs: list[CompactPack],
    reference_sop_packs: list[CompactPack],
    *,
    context_block: str,
    case_intake: dict[str, str] | None = None,
) -> str:
    patient_lines = [f"- {pack.title}: {pack.summary[:400]}" for pack in patient_packs[:12]]
    sop_lines = [f"- {pack.title}: {pack.summary[:400]}" for pack in reference_sop_packs[:8]]

    return f"""You are building a perioperative MILESTONE checklist for an OR voice logger.
The checklist must span BEFORE, DURING, and AFTER surgery — not pre-op steps only.

Procedure: {procedure}

Case intake form (use for patient-specific pre-op safety milestones):
{_format_case_intake(case_intake)}

Patient context (tailoring only — do NOT turn chart sections into steps):
{chr(10).join(patient_lines) or "- None"}

Reference operative workflow / SOP (derive broad phase names only):
{chr(10).join(sop_lines) or "- Standard TKA workflow"}

Condensed case context:
{context_block[:6000] if context_block else "None"}

Return ONLY valid JSON with this shape:
{{
  "procedure": "{procedure}",
  "mode": "logger",
  "steps": [
    {{"id": "unique_snake_case_id", "label": "Short milestone name", "aliases": ["spoken", "alias"]}}
  ]
}}

Rules:
- Generate 8–10 MAJOR milestones in strict chronological order across all three phases: pre-op safety → intra-operative phases → post-op handoff/recovery.
- Never exceed 10 steps.
- CRITICAL: Derive steps from THIS patient's comorbidities, allergies, procedure, surgeon notes, and chart excerpts above.
  If penicillin allergy → include explicit allergy/antibiotic verification. If diabetes → note glucose/DVT where relevant.
  Do NOT output a generic TKA template identical for every case.
- Do NOT copy placeholder ids like "timeout" unless they fit; invent ids from the milestone label.
- Do NOT stop at closure; include at least one post-op milestone (PACU handoff, post-op orders, or discharge planning).
- NEVER include granular intraoperative actions as checklist rows.
- NEVER use H&P headings, demographics, MRN, or examination sections as steps.
- Each step needs a stable snake_case id and 2–4 voice aliases for milestone matching.
"""


async def generate_checklist(
    procedure: str,
    patient_packs: list[CompactPack],
    reference_sop_packs: list[CompactPack],
    *,
    context_block: str = "",
    case_intake: dict[str, str] | None = None,
) -> dict:
    """LLM-generated pre/intra/post-op milestones; falls back to default TKA steps."""
    prompt = _build_prompt(
        procedure,
        patient_packs,
        reference_sop_packs,
        context_block=context_block,
        case_intake=case_intake,
    )
    raw = await asyncio.to_thread(converse_text, prompt, max_tokens=1600, temperature=0.2)
    if raw:
        parsed = _parse_checklist_json(raw, procedure)
        if parsed:
            logger.info("Generated %d checklist steps via %s LLM", len(parsed["steps"]), "Nebius/MiniMax")
            return parsed
        logger.warning(
            "Checklist LLM response did not parse (%d chars); using default TKA fallback. Preview: %s",
            len(raw),
            raw[:240].replace("\n", " "),
        )
    else:
        logger.warning("Checklist LLM unavailable; using default TKA fallback")
    return default_checklist(procedure, reason="default_tka_fallback")
