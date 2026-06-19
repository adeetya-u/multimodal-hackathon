"""Landing demo voice — general knee education, no patient chart."""

from __future__ import annotations

from .llm import converse_intro, converse_text
from .prompts import build_intro_answer_prompt
from .search import KnowledgeSearch, load_demo_reference_knowledge, rerank_snippets
from .workers import AnswerResult, clamp_spoken_text, parse_grounded_response
import asyncio


_demo_knowledge_cache: KnowledgeSearch | None = None


def _get_demo_knowledge() -> KnowledgeSearch:
    global _demo_knowledge_cache
    if _demo_knowledge_cache is None:
        _demo_knowledge_cache = load_demo_reference_knowledge()
    return _demo_knowledge_cache


def format_intro_candidates(candidates: list) -> str:
    lines: list[str] = []
    for snip in candidates[:6]:
        cid = snip.chunk_id or snip.source
        lines.append(f"{cid} | {snip.source} | {snip.doc_type} | {snip.text[:400]}")
    return "\n".join(lines) if lines else "(no reference excerpts)"


async def answer_intro_question(text: str) -> str:
    """Answer a general orthopedics question using reference corpus only."""
    cleaned = text.strip()
    if not cleaned:
        return ""

    knowledge = _get_demo_knowledge()
    candidates = await knowledge.search(cleaned, k=8, prefer_sop=True, prefer_patient=False)
    survivors = rerank_snippets(cleaned, candidates, prefer_patient=False)

    if survivors:
        prompt = build_intro_answer_prompt(
            question=cleaned,
            reference_excerpts=format_intro_candidates(survivors),
        )
        raw = await asyncio.to_thread(converse_text, prompt, max_tokens=180, temperature=0.2)
        if raw:
            parsed = parse_grounded_response(raw)
            if isinstance(parsed, AnswerResult) and parsed.spoken_text.strip() and not parsed.refusal:
                return clamp_spoken_text(parsed.spoken_text)

    spoken = converse_intro(cleaned)
    if spoken and spoken.strip():
        return clamp_spoken_text(spoken)
    return clamp_spoken_text(
        "For patient-specific answers, continue to prep and upload a chart. "
        "Typical TKA rehab starts with early mobilization and progresses over several weeks."
    )
