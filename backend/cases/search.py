from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .store import case_data_root
from .types import Snippet


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


_PATIENT_DOC_TYPES = frozenset({"patient", "manual", "comorbidity"})


def _type_boost(snip: Snippet, *, prefer_patient: bool, prefer_sop: bool) -> float:
    boost = 0.0
    if prefer_patient and snip.doc_type in _PATIENT_DOC_TYPES:
        boost += 0.35
    if prefer_sop and snip.doc_type in {"sop", "standard_text", "evidence"}:
        boost += 0.15
    return boost


def merge_snippet_hits(*groups: list[Snippet], limit: int = 8) -> list[Snippet]:
    merged: list[Snippet] = []
    seen: set[str] = set()
    for group in groups:
        for snip in group:
            key = (snip.chunk_id or snip.source or snip.title).lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(snip)
            if len(merged) >= limit:
                return merged
    return merged


class KnowledgeSearch:
    """Local keyword search over moss_snippets.json — no external vector DB required."""

    def __init__(self, snippets: list[Snippet] | None = None, *, index_name: str = "local") -> None:
        self._snippets = list(snippets or [])
        self._index_name = index_name
        self._live_events: list[tuple[str, str]] = []

    @classmethod
    def from_case_dir(cls, case_dir: Path) -> KnowledgeSearch:
        path = case_dir / "moss_snippets.json"
        if not path.exists():
            return cls([], index_name=case_dir.name)
        raw = json.loads(path.read_text(encoding="utf-8"))
        snippets = [Snippet.from_dict(item) for item in raw if isinstance(item, dict)]
        return cls(snippets, index_name=case_dir.name)

    async def warmup(self) -> None:
        return

    def replace_corpus(self, snippets: list[Snippet], *, index_name: str) -> bool:
        if not snippets:
            return False
        self._snippets = list(snippets)
        self._index_name = index_name
        return True

    def sync_live_events(self, events: list[tuple[str, str]]) -> None:
        self._live_events = events[-48:]

    async def search(
        self,
        query: str,
        k: int = 5,
        *,
        prefer_sop: bool = False,
        prefer_patient: bool = False,
    ) -> list[Snippet]:
        tokens = _tokenize(query)
        if not tokens:
            return self._snippets[:k]

        scored: list[tuple[float, Snippet]] = []
        for snip in self._snippets:
            hay = f"{snip.title} {snip.text} {snip.source} {snip.doc_type}".lower()
            hay_tokens = _tokenize(hay)
            overlap = len(tokens & hay_tokens)
            if overlap == 0:
                continue
            score = overlap / max(len(tokens), 1)
            score += _type_boost(snip, prefer_patient=prefer_patient, prefer_sop=prefer_sop)
            scored.append((score, Snippet(**{**snip.__dict__, "score": score})))

        for event_type, text in self._live_events[-12:]:
            hay_tokens = _tokenize(text)
            overlap = len(tokens & hay_tokens)
            if overlap == 0:
                continue
            score = overlap / max(len(tokens), 1) + 0.05
            scored.append(
                (
                    score,
                    Snippet(
                        source=f"session/{event_type}",
                        text=text,
                        score=score,
                        chunk_id=f"live-{len(scored)}",
                        doc_type="session",
                        title="Live case log",
                    ),
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [snip for _, snip in scored[:k]]


def load_case_knowledge(case_id: str | None) -> KnowledgeSearch:
    if case_id:
        case_dir = case_data_root() / case_id
        if case_dir.exists():
            return KnowledgeSearch.from_case_dir(case_dir)
    return KnowledgeSearch([], index_name="empty")


def load_demo_reference_knowledge() -> KnowledgeSearch:
    """Reference knee corpus for landing demo — no patient chart."""
    from shared.bootstrap import BACKEND_ROOT

    path = BACKEND_ROOT / "assets" / "reference" / "knee_corpus_compact.json"
    if not path.exists():
        return KnowledgeSearch([], index_name="knee-reference")
    raw = json.loads(path.read_text(encoding="utf-8"))
    packs = raw.get("packs") if isinstance(raw, dict) else raw
    if not isinstance(packs, list):
        return KnowledgeSearch([], index_name="knee-reference")
    snippets = []
    for item in packs:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or item.get("id") or "")
        doc_type = str(item.get("doc_type") or item.get("chunk_type") or "")
        snippets.append(
            Snippet.from_dict(
                {
                    **item,
                    "chunk_id": chunk_id,
                    "doc_type": doc_type,
                }
            )
        )
    return KnowledgeSearch(snippets, index_name="knee-reference")


def rerank_snippets(query: str, candidates: list[Snippet], *, prefer_patient: bool = True) -> list[Snippet]:
    tokens = _tokenize(query)
    if not tokens:
        return candidates
    rescored: list[tuple[float, Snippet]] = []
    for snip in candidates:
        hay_tokens = _tokenize(f"{snip.title} {snip.text}")
        overlap = len(tokens & hay_tokens)
        score = overlap / max(len(tokens), 1) + snip.score * 0.5
        if prefer_patient and snip.doc_type in _PATIENT_DOC_TYPES:
            score += 0.25
        rescored.append((score, Snippet(**{**snip.__dict__, "score": score})))
    rescored.sort(key=lambda item: item[0], reverse=True)
    return [snip for score, snip in rescored if score > 0.1]


def find_grounded_snippet(snippets: list[Snippet], chunk_ids: list[str]) -> Snippet | None:
    if not chunk_ids:
        return None
    wanted = {c.lower() for c in chunk_ids}
    for snip in snippets:
        cid = (snip.chunk_id or snip.source.split("/")[-1]).lower()
        if cid in wanted:
            return snip
    return snippets[0] if len(snippets) == 1 else None


def situation_card_from_snippet(snip: Snippet) -> dict:
    text = snip.text[:1200]
    return {
        "title": snip.title or snip.source,
        "body": text,
        "excerpt": text,
        "citation": snip.source,
        "source": snip.source,
        "chunk_id": snip.chunk_id or snip.source,
        "doc_type": snip.doc_type,
    }


def grounded_display_payload(snip: Snippet, *, spoken_text: str, confidence: float) -> dict:
    card = situation_card_from_snippet(snip)
    kind = "guideline" if snip.guideline_ref else "text"
    payload = {
        "chunk_id": snip.chunk_id or snip.source,
        "spoken_text": spoken_text,
        "confidence": confidence,
        "kind": kind,
        **card,
    }
    if snip.guideline_ref:
        page = 1
        if snip.pages:
            try:
                page = int(str(snip.pages).split(",")[0])
            except ValueError:
                pass
        payload["guideline"] = {
            "pdf_url": snip.guideline_ref if snip.guideline_ref.startswith("http") else "",
            "page": page,
            "highlight_snippet": snip.text[:200],
        }
    return payload


def external_display_payload(*, spoken_text: str, source: str, excerpt: str) -> dict:
    text = excerpt[:1200]
    return {
        "chunk_id": "external",
        "spoken_text": spoken_text,
        "confidence": 0.45,
        "kind": "external",
        "title": "External reference",
        "body": text,
        "excerpt": text,
        "citation": source,
        "source": source or "external reference",
    }


def clear_display_payload() -> dict:
    return {"chunk_id": None, "cards": []}


def load_case_corpus(case_dir: Path) -> list[Snippet]:
    path = case_dir / "moss_snippets.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Snippet.from_dict(item) for item in raw if isinstance(item, dict)]
