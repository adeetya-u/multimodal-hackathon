"""Extract short case intake fields from uploaded patient chart text."""

from __future__ import annotations

import asyncio
import json
import logging
import re

logger = logging.getLogger(__name__)

MAX_FIELD_WORDS = 6


def clip_words(text: str, max_words: int = MAX_FIELD_WORDS) -> str:
    words = re.split(r"\s+", (text or "").strip())
    return " ".join(words[:max_words]) if words else ""


def _after_thinking(text: str) -> str:
    lowered = text.lower()
    for tag in ("redacted_thinking", "think"):
        marker = f"</{tag}>"
        idx = lowered.rfind(marker)
        if idx >= 0:
            return text[idx + len(marker) :].strip()
    return text.strip()


def _strip_llm_noise(text: str) -> str:
    cleaned = _after_thinking(text)
    cleaned = re.sub(
        r"<\s*redacted_thinking\s*>.*?<\s*/\s*redacted_thinking\s*>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_intake_json(text: str) -> dict | None:
    for candidate in (_strip_llm_noise(text), text.strip()):
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
            if isinstance(data, dict):
                return data
            continue
        if isinstance(data, dict):
            return data
    return None


def _normalize_comorbidities(raw: object) -> list[str]:
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        items = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    clipped = [clip_words(item) for item in items if clip_words(item)]
    return clipped[:3]


def _call_intake_llm(prompt: str) -> str | None:
    from .llm import _openai_client_instance, resolve_model

    try:
        client = _openai_client_instance()
        model = resolve_model("default")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Reply with a single JSON object only. No reasoning or markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.1,
        )
        content = response.choices[0].message.content if response.choices else None
        return content.strip() if content else None
    except Exception as exc:
        logger.warning("Intake LLM call failed: %s", exc)
        return None


async def extract_case_intake_from_text(chart_text: str) -> dict[str, object]:
    """Return patient_id, procedure, comorbidities, manual_notes — each capped at ~6 words."""
    sample = chart_text.strip()[:10000]
    if not sample:
        return {}

    prompt = f"""Extract case intake from this patient chart.

Return JSON:
{{
  "patient_id": "short id",
  "procedure": "planned surgery",
  "comorbidities": ["condition one", "condition two"],
  "manual_notes": "allergies or plan highlight"
}}

Each value: at most {MAX_FIELD_WORDS} words. Comorbidities: 1-3 short items.

Chart:
{sample}
"""

    raw = await asyncio.to_thread(_call_intake_llm, prompt)
    if not raw:
        return {}

    parsed = _parse_intake_json(raw)
    if not parsed:
        logger.warning("Case intake LLM response did not parse: %s", raw[:200])
        return {}

    patient_id = clip_words(str(parsed.get("patient_id") or ""))
    procedure = clip_words(str(parsed.get("procedure") or ""))
    notes = clip_words(str(parsed.get("manual_notes") or ""))
    comorbidities = _normalize_comorbidities(parsed.get("comorbidities"))

    return {
        "patient_id": patient_id,
        "procedure": procedure,
        "comorbidities": comorbidities,
        "manual_notes": notes,
    }
