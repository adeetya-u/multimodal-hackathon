"""Safety checks on spoken clinical answers — block contradictions with chart."""

from __future__ import annotations

import re


def chart_documents_penicillin_allergy(text: str) -> bool:
    lower = text.lower()
    if "penicillin" not in lower and "beta-lactam" not in lower and "beta lactam" not in lower:
        return False
    if re.search(r"penicillin.{0,40}allerg|allerg.{0,40}penicillin", lower):
        return True
    if re.search(r"\b(?:avoid|contraind).{0,30}penicillin", lower):
        return True
    return "documented penicillin allergy" in lower


def spoken_denies_penicillin_allergy(text: str) -> bool:
    lower = text.lower()
    patterns = (
        r"\bno (?:known )?(?:penicillin )?allerg",
        r"\bnkda\b",
        r"\bwithout (?:any )?allerg",
        r"\bno penicillin",
        r"\bnot allergic to penicillin",
        r"\bincluding no penicillin allergy",
        r"\bdenies penicillin",
        r"\bno documented allerg",
    )
    return any(re.search(p, lower) for p in patterns)


def chart_text_for_guard(summary: str, raw: dict | None = None) -> str:
    """Combine chart summary and raw patient context for allergy checks."""
    parts: list[str] = []
    if summary.strip():
        parts.append(summary.strip())
    if raw:
        for key in ("notes", "comorbidities"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
            elif isinstance(val, list):
                parts.extend(str(item) for item in val if str(item).strip())
        for pack in raw.get("compact_packs") or []:
            if isinstance(pack, dict):
                title = str(pack.get("title") or "").strip()
                body = str(pack.get("summary") or "").strip()
                if title or body:
                    parts.append(f"{title} {body}".strip())
    return "\n".join(parts)


def guard_spoken_against_chart(spoken: str, chart_summary: str, *, raw_context: dict | None = None) -> str:
    """Replace spoken text that contradicts documented penicillin allergy."""
    if not spoken.strip():
        return spoken
    chart_blob = chart_text_for_guard(chart_summary, raw_context)
    if not chart_blob.strip():
        return spoken
    if chart_documents_penicillin_allergy(chart_blob) and spoken_denies_penicillin_allergy(spoken):
        return "Chart documents penicillin allergy — see the cited source on screen."
    return spoken
