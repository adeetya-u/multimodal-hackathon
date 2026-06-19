"""Deterministic answers from indexed patient chart text — avoid false MISSING responses."""

from __future__ import annotations

import re

from .bootstrap import SurgeryContext
from .clinical_guard import chart_text_for_guard
from .workers import clamp_spoken_text

_MED_QUERY = re.compile(
    r"\b("
    r"medications?|meds|home meds|current meds|"
    r"what (?:is she|is he|are they|is the patient) on|"
    r"what(?:'s| is) (?:she|he|the patient) taking|"
    r"drug list|prescriptions?"
    r")\b",
    re.I,
)


def _chart_blob(ctx: SurgeryContext) -> str:
    window = ctx.raw.get("context_window") if ctx.raw else None
    extra = ""
    if isinstance(window, dict):
        extra = str(window.get("prompt_block") or "")
    base = chart_text_for_guard(ctx.summary, ctx.raw)
    if extra.strip() and extra.strip() not in base:
        return f"{base}\n{extra.strip()}".strip()
    return base


def _section_after_header(blob: str, header: re.Pattern[str], *, max_chars: int = 2200) -> str | None:
    match = header.search(blob)
    if not match:
        return None
    tail = blob[match.start() : match.start() + max_chars]
    next_section = re.search(r"\n##\s+\d+\.", tail[20:])
    if next_section:
        tail = tail[: 20 + next_section.start()]
    return tail.strip()


def _drugs_from_med_section(section: str) -> list[str]:
    drugs: list[str] = []
    for line in section.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0].lower() not in {"drug", "---", "medication"}:
                name = re.sub(r"\*\*", "", cells[0]).strip()
                dose = cells[1].strip() if len(cells) > 1 else ""
                if name and not name.startswith("-"):
                    drugs.append(f"{name} {dose}".strip())
            continue
        bullet = re.match(r"^[-*•]\s+(.+)$", line)
        if bullet:
            drugs.append(bullet.group(1).strip()[:80])
    return drugs


def extract_medications_spoken(ctx: SurgeryContext) -> str | None:
    blob = _chart_blob(ctx)
    if not blob.strip():
        return None
    section = _section_after_header(
        blob,
        re.compile(r"(?:^|\n)#+\s*[\d.]*\s*Medications?\b[^\n]*", re.I | re.M),
    )
    if not section and "metformin" not in blob.lower() and "lisinopril" not in blob.lower():
        if not re.search(r"\bmedications?\b", blob, re.I):
            return None
        section = blob
    drugs = _drugs_from_med_section(section or blob)
    if not drugs:
        # Fallback: named agents commonly documented in demo/production charts
        named = []
        for pattern in (
            r"\b(metformin(?:\s+\d+\s*(?:mg|g)[^|\n.]*)?)",
            r"\b(lisinopril(?:\s+\d+\s*mg[^|\n.]*)?)",
            r"\b(amlodipine(?:\s+\d+\s*mg[^|\n.]*)?)",
            r"\b(levothyroxine(?:\s+\d+\s*(?:mcg|mg)[^|\n.]*)?)",
            r"\b(atorvastatin(?:\s+\d+\s*mg[^|\n.]*)?)",
            r"\b(aspirin(?:\s+\d+\s*mg[^|\n.]*)?)",
        ):
            m = re.search(pattern, blob, re.I)
            if m:
                named.append(m.group(1).strip())
        if not named:
            return None
        drugs = named
    if len(drugs) == 1:
        spoken = f"Current medications include {drugs[0]}."
    elif len(drugs) == 2:
        spoken = f"Current medications include {drugs[0]} and {drugs[1]}."
    else:
        spoken = f"Current medications include {', '.join(drugs[:-1])}, and {drugs[-1]}."
    hold_note = ""
    lower = (section or blob).lower()
    if "withhold" in lower and "metformin" in lower:
        hold_note = " Metformin is withheld the morning of surgery."
    elif "withhold" in lower:
        hold_note = " Some home meds are held peri-operatively per the chart."
    return clamp_spoken_text(spoken + hold_note, max_lines=2, max_chars=180)


def try_chart_fact_answer(query: str, ctx: SurgeryContext | None) -> str | None:
    if not ctx or not query.strip():
        return None
    if _MED_QUERY.search(query):
        return extract_medications_spoken(ctx)
    return None
