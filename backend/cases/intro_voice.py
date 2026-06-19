"""Landing demo voice — general knee education, no patient chart."""

from __future__ import annotations

import asyncio
import re

from .llm import converse_intro
from .search import KnowledgeSearch, load_demo_reference_knowledge, rerank_snippets
from .types import Snippet
from .workers import clamp_spoken_text


_demo_knowledge_cache: KnowledgeSearch | None = None


def _get_demo_knowledge() -> KnowledgeSearch:
    global _demo_knowledge_cache
    if _demo_knowledge_cache is None:
        _demo_knowledge_cache = load_demo_reference_knowledge()
    return _demo_knowledge_cache


async def warm_intro_demo() -> None:
    """Preload reference index so first demo question is fast."""
    _get_demo_knowledge()


def format_intro_candidates(candidates: list) -> str:
    lines: list[str] = []
    for snip in candidates[:6]:
        cid = snip.chunk_id or snip.source
        lines.append(f"{cid} | {snip.source} | {snip.doc_type} | {snip.text[:400]}")
    return "\n".join(lines) if lines else "(no reference excerpts)"


def clamp_intro_spoken(text: str) -> str:
    """Demo voice — one short sentence preferred, two lines max."""
    return clamp_spoken_text(text, max_lines=2, max_chars=180)


def _question_keywords(question: str) -> list[str]:
    q = question.lower()
    keys = (
        "recover",
        "rehab",
        "week",
        "month",
        "day",
        "timeline",
        "return",
        "dvt",
        "infection",
        "pain",
        "partial",
        "total",
        "replacement",
        "tka",
        "acl",
    )
    return [k for k in keys if k in q]


def _score_intro_sentence(sentence: str, question: str) -> int:
    s = sentence.lower()
    q = question.lower()
    score = 0
    if re.search(r"\b\d+\s*(?:day|week|month|year)s?\b", s):
        score += 6
    if "rehab" in s or "rehabilitation" in s:
        score += 4
    if any(term in s for term in ("weight bear", "walking", "mobiliz", "discharge", "return to")):
        score += 3
    if any(term in q for term in ("how long", "recover", "timeline", "rehab")):
        if any(term in s for term in ("week", "month", "day", "rehab", "walking", "weight bear")):
            score += 4
        if any(term in s for term in ("palsy", "spontaneously", "incidence", "prevalence")):
            score -= 8
    for key in _question_keywords(question):
        if key in s:
            score += 2
    return score


def _snippet_sentence(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    if not cleaned:
        return None
    for match in re.finditer(r"[^.!?]{35,220}[.!?]", cleaned):
        sentence = match.group(0).strip()
        if len(sentence.split()) >= 6:
            return sentence
    if len(cleaned) >= 35:
        return cleaned[:220].rstrip(" ,;") + ("…" if len(cleaned) > 220 else ".")
    return None


def intro_snippet_fallback(question: str, survivors: list[Snippet]) -> str:
    """Speak from reference excerpts when the LLM is unavailable."""
    best_sentence = ""
    best_score = 0
    for snip in survivors:
        for sentence in re.split(r"(?<=[.!?])\s+", snip.text.replace("\n", " ")):
            s = sentence.strip()
            if len(s.split()) < 6:
                continue
            score = _score_intro_sentence(s, question)
            if score > best_score:
                picked = _snippet_sentence(s)
                if picked:
                    best_score = score
                    best_sentence = picked
    if best_sentence and best_score > 0:
        return clamp_intro_spoken(best_sentence)
    for snip in survivors:
        picked = _snippet_sentence(snip.text)
        if picked:
            return clamp_intro_spoken(picked)
    return clamp_intro_spoken(
        "After knee surgery, many people walk within days and return to daily activity over about twelve weeks."
    )


async def answer_intro_question(text: str) -> str:
    """Answer a general orthopedics question using reference corpus only."""
    cleaned = text.strip()
    if not cleaned:
        return ""

    knowledge = _get_demo_knowledge()
    candidates = await knowledge.search(cleaned, k=6, prefer_sop=True, prefer_patient=False)
    survivors = rerank_snippets(cleaned, candidates, prefer_patient=False)

    if survivors:
        excerpts = format_intro_candidates(survivors[:3])
        spoken = await asyncio.to_thread(converse_intro, cleaned, reference_excerpts=excerpts)
        if spoken and spoken.strip():
            return clamp_intro_spoken(spoken)
        return intro_snippet_fallback(cleaned, survivors)

    spoken = await asyncio.to_thread(converse_intro, cleaned)
    if spoken and spoken.strip():
        return clamp_intro_spoken(spoken)

    return clamp_intro_spoken(
        "After knee surgery, many people walk within days and return to daily activity over about twelve weeks."
    )
