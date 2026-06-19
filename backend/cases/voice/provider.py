"""Vapi voice provider configuration."""

from __future__ import annotations

import os
from typing import Any

from ..bootstrap import load_case_context
from ..checklist import load_case_checklist


def or_assistant_id() -> str:
    return os.environ.get("VAPI_OR_ASSISTANT_ID", "").strip()


def intro_assistant_id() -> str:
    return os.environ.get("VAPI_INTRO_ASSISTANT_ID", "").strip()


def public_key() -> str:
    return os.environ.get("VAPI_PUBLIC_KEY", "").strip()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def transcriber_config() -> dict[str, Any]:
    """Deepgram via Vapi — nova-3-medical for OR/clinical vocabulary."""
    endpointing_ms = _env_int("VAPI_TRANSCRIBER_ENDPOINTING_MS", 500)
    return {
        "provider": "deepgram",
        "model": os.environ.get("VAPI_TRANSCRIBER_MODEL", "nova-3-medical").strip(),
        "language": "en",
        "endpointing": endpointing_ms,
        "smartFormat": True,
        "keywords": [
            "Scalpel",
            "allergies",
            "allergy",
            "penicillin",
            "arthroplasty",
            "checklist",
            "DVT",
            "antibiotic",
        ],
        "fallbackPlan": {"autoFallback": {"enabled": True}},
    }


def voice_pipeline_config() -> dict[str, Any]:
    """Vapi turn-taking — longer waits before cutting off surgeon or agent mid-sentence."""
    return {
        "startSpeakingPlan": {
            "waitSeconds": _env_float("VAPI_START_WAIT_SEC", 0.5),
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": _env_float("VAPI_ENDPOINT_PUNCT_SEC", 0.65),
                # Vapi rejects values > 3 for onNoPunctuationSeconds.
                "onNoPunctuationSeconds": _clamp(
                    _env_float("VAPI_ENDPOINT_NO_PUNCT_SEC", 2.8),
                    0.1,
                    3.0,
                ),
                "onNumberSeconds": _env_float("VAPI_ENDPOINT_NUMBER_SEC", 1.5),
            },
        },
        "stopSpeakingPlan": {
            # Require a few transcribed words before interrupting the agent (OR noise / thinking aloud).
            "numWords": _env_int("VAPI_STOP_NUM_WORDS", 4),
            "voiceSeconds": _env_float("VAPI_STOP_VOICE_SEC", 0.45),
            "backoffSeconds": _env_float("VAPI_STOP_BACKOFF_SEC", 1.4),
            "acknowledgementPhrases": [
                "okay",
                "right",
                "uh-huh",
                "yeah",
                "mm-hmm",
                "got it",
                "noted",
            ],
        },
    }


def _checklist_summary(case_id: str) -> str:
    checklist = load_case_checklist(case_id)
    if not checklist.steps:
        return "No operative milestones loaded."
    parts = [f"{index + 1}. {step.label}" for index, step in enumerate(checklist.steps[:10])]
    return "; ".join(parts)


def _chart_summary(case_id: str) -> str:
    ctx = load_case_context(case_id)
    summary = ctx.summary.strip()
    if not summary:
        return "No chart summary loaded."
    if len(summary) > 700:
        return summary[:700] + "…"
    return summary


def _system_prompt() -> str:
    return (
        "You are Scalpel, the OR voice assistant. The surgical case is already loaded — "
        "never ask for patient ID, case ID, chart upload, or case setup.\n\n"
        "Patient ID: {{patient_id}}\n"
        "Procedure: {{procedure}}\n"
        "Chart highlights: {{chart_summary}}\n"
        "Operative checklist: {{checklist_summary}}\n\n"
        "Rules:\n"
        "- When the surgeon reports step progress, respond with one short acknowledgment like "
        '"Noted." or "Got it."\n'
        "- When the surgeon asks a clinical question, respond ONLY with "
        '"Checking." or "One moment." — never answer clinically yourself; the screen shows the grounded answer.\n'
        "- Do not invent clinical facts. Do not deny or affirm allergies, meds, or labs from memory.\n"
        "- Do not repeat the patient name or procedure unless the surgeon asks."
    )


def _first_message() -> str:
    return "Scalpel is ready. Report a checklist step or ask a clinical question."


def _intro_system_prompt() -> str:
    return (
        "You are Scalpel on the public knee surgery demo. There is NO patient chart.\n\n"
        "Rules:\n"
        "- For greetings or meta questions (what can you do, hello), reply in one short sentence. "
        "Mention they can ask general knee surgery questions or continue to prep for a full case.\n"
        "- For ANY clinical or medical question, respond ONLY with "
        '"Let me look that up." — never answer clinically yourself; the app delivers the answer.\n'
        '- Never say "Checking.", "One moment.", or ask for patient ID or chart upload.\n'
        "- Do not invent clinical facts."
    )


def _intro_first_message() -> str:
    return "Hi — I'm Scalpel. Ask anything about knee surgery, or continue to prep for a full case."


def intro_assistant_overrides() -> dict[str, Any]:
    """Landing demo — general knee Q&A, no case chart or OR webhook."""
    return {
        "metadata": {"mode": "intro"},
        **voice_pipeline_config(),
        "transcriber": transcriber_config(),
        "clientMessages": [
            "transcript",
            "speech-update",
            "conversation-update",
            "status-update",
            "hang",
        ],
        "firstMessage": _intro_first_message(),
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": _intro_system_prompt()}],
        },
    }


def assistant_overrides(case_id: str) -> dict[str, Any]:
    ctx = load_case_context(case_id)
    patient_id = ctx.patient_id if ctx.patient_id not in {"", "UNKNOWN"} else case_id
    procedure = ctx.procedure if ctx.procedure not in {"", "Unknown"} else "Surgery"
    checklist_summary = _checklist_summary(case_id)
    chart_summary = _chart_summary(case_id)
    variable_values = {
        "case_id": case_id,
        "patient_id": patient_id,
        "procedure": procedure,
        "checklist_summary": checklist_summary,
        "chart_summary": chart_summary,
    }
    return {
        "metadata": {"case_id": case_id},
        "variableValues": variable_values,
        **voice_pipeline_config(),
        "transcriber": transcriber_config(),
        "clientMessages": [
            "transcript",
            "speech-update",
            "conversation-update",
            "status-update",
            "hang",
        ],
        "firstMessage": _first_message(),
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": _system_prompt()}],
        },
    }


def voice_start_payload(case_id: str) -> dict[str, Any]:
    """Config returned to web client for Vapi.start()."""
    ctx = load_case_context(case_id)
    patient_id = ctx.patient_id if ctx.patient_id not in {"", "UNKNOWN"} else case_id
    procedure = ctx.procedure if ctx.procedure not in {"", "Unknown"} else "Surgery"
    return {
        "provider": "vapi",
        "assistantId": or_assistant_id(),
        "publicKey": public_key(),
        "metadata": {"case_id": case_id},
        "caseContext": {
            "case_id": case_id,
            "patient_id": patient_id,
            "procedure": procedure,
            "checklist_summary": _checklist_summary(case_id),
            "chart_summary": _chart_summary(case_id),
        },
        "assistantOverrides": assistant_overrides(case_id),
    }


def voice_status() -> dict[str, Any]:
    configured = bool(public_key() and or_assistant_id())
    return {
        "provider": "vapi",
        "voice_ready": configured,
        "agent_in_room": configured,
        "agent_count": 1 if configured else 0,
    }
