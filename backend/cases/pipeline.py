from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pypdf

from .case_intake_extract import extract_case_intake_from_text
from .checklist_gen import generate_checklist
from .store import CaseStore, IngestionStage
from .types import CompactPack, Snippet

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAX_REFERENCE_PACKS = int(os.environ.get("KNEE_REFERENCE_PACK_LIMIT", "40"))


async def run_ingestion_pipeline(store: CaseStore, case_id: str) -> None:
    meta = store.get_metadata(case_id)
    store.update_stage(case_id, IngestionStage.PARSING)

    raw_dir = store.case_dir(case_id) / "raw"
    doc_chunks: list[dict] = []
    chart_text_parts: list[str] = []

    for doc_name in meta.documents:
        parsed_chunks = await _parse_document(raw_dir / doc_name)
        doc_chunks.extend(parsed_chunks)
        chart_text_parts.extend(str(c.get("text", "")) for c in parsed_chunks if c.get("text"))

    chart_text = "\n\n".join(chart_text_parts)
    if chart_text.strip():
        extracted = await extract_case_intake_from_text(chart_text)
        if extracted:
            patient_id = str(extracted.get("patient_id") or "").strip() or meta.patient_id
            procedure = str(extracted.get("procedure") or "").strip() or meta.procedure
            notes = str(extracted.get("manual_notes") or "").strip() or meta.manual_notes
            comorbidities = extracted.get("comorbidities")
            if not isinstance(comorbidities, list) or not comorbidities:
                comorbidities = meta.comorbidities
            store.update_case_details(
                case_id,
                patient_id=patient_id,
                procedure=procedure,
                manual_notes=notes,
                comorbidities=comorbidities,
            )
            meta = store.get_metadata(case_id)
            logger.info(
                "Case %s intake extracted: procedure=%r comorbidities=%s",
                case_id,
                meta.procedure,
                meta.comorbidities,
            )

    chunks: list[dict] = [
        {
            "id": "case-intake",
            "chunk_type": "patient",
            "title": "Case intake form",
            "text": (
                f"Patient ID: {meta.patient_id}\n"
                f"Procedure: {meta.procedure}\n"
                f"Comorbidities: {', '.join(meta.comorbidities) or 'None'}\n"
                f"Surgeon notes: {meta.manual_notes or 'None'}"
            ),
            "source_file": "case-form",
        }
    ]

    chunks.extend(doc_chunks)

    if meta.manual_notes.strip():
        chunks.append(
            {
                "id": "manual-notes",
                "chunk_type": "manual",
                "title": "Surgeon manual notes",
                "text": meta.manual_notes,
                "source_file": "manual",
            }
        )

    store.update_stage(case_id, IngestionStage.COMPACTING)
    patient_packs = [await _compact_chunk(c) for c in chunks]
    reference_packs = _load_knee_reference_packs(meta.procedure)
    packs = patient_packs + reference_packs
    store.write_json(case_id, "compact_context.json", [asdict(p) for p in packs])

    context_window = _build_context_window(packs, meta.procedure)
    store.write_json(case_id, "context_window.json", context_window)

    sop_packs = [p for p in reference_packs if p.chunk_type == "sop"] or reference_packs[:8]
    case_intake = {
        "patient_id": meta.patient_id,
        "procedure": meta.procedure,
        "comorbidities": ", ".join(meta.comorbidities) or "None",
        "notes": meta.manual_notes or "",
    }
    checklist = await generate_checklist(
        meta.procedure,
        patient_packs,
        sop_packs,
        context_block=context_window.get("prompt_block", ""),
        case_intake=case_intake,
    )
    store.write_json(case_id, "checklist.json", checklist)

    patient_context = {
        "patient_id": meta.patient_id,
        "procedure": meta.procedure,
        "comorbidities": meta.comorbidities,
        "notes": meta.manual_notes,
        "compact_packs": [asdict(p) for p in patient_packs],
        "context_window": context_window,
    }
    store.write_json(case_id, "patient_context.json", patient_context)

    store.update_stage(case_id, IngestionStage.INDEXING)
    snippets = _build_snippets(packs, meta.patient_id)
    store.write_json(case_id, "moss_snippets.json", [s.to_dict() for s in snippets])

    uploaded = [name for name in meta.documents if name != "case-form"]
    logger.info(
        "Case %s indexed %d patient chunk(s) from %d uploaded file(s)",
        case_id,
        sum(1 for p in patient_packs if p.chunk_type in {"patient", "manual"} and p.id != "case-intake"),
        len(uploaded),
    )

    store.update_stage(case_id, IngestionStage.READY)
    logger.info(
        "Case %s ready (%d packs, %d snippets, %d checklist steps)",
        case_id,
        len(packs),
        len(snippets),
        len(checklist.get("steps", [])),
    )


async def _parse_document(path: Path) -> list[dict]:
    if not path.exists():
        return []
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return _split_text_chunks(text, path.name, "patient")

    if suffix == ".pdf":
        chunks = await _parse_pdf_document(path)
        if chunks:
            return chunks
        logger.warning("PDF parse returned no chunks for %s", path.name)
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    return _split_text_chunks(text[:8000], path.name, "patient")


async def _parse_pdf_document(path: Path) -> list[dict]:
    """Extract full raw text locally (no Unsiloed)."""
    return _parse_pdf_local(path)


def _parse_pdf_local(path: Path) -> list[dict]:
    reader = pypdf.PdfReader(str(path))
    pages = [page.extract_text().strip() for page in reader.pages if page.extract_text()]
    text = "\n\n".join(pages)
    if not text.strip():
        return []
    stem = path.stem.replace("_", " ").replace("-", " ")
    return [
        {
            "id": path.stem,
            "chunk_type": "patient",
            "title": stem or path.name,
            "text": text,
            "source_file": path.name,
        }
    ]


def _split_text_chunks(text: str, filename: str, chunk_type: str) -> list[dict]:
    max_chars = int(os.environ.get("UNSILOED_MAX_CHUNK_CHARS", "1200"))
    min_chars = int(os.environ.get("PATIENT_MIN_CHUNK_CHARS", "80"))
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")

    sections: list[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    buf: list[str] = []
    for para in paragraphs:
        candidate = "\n\n".join([*buf, para]) if buf else para
        if buf and len(candidate) > max_chars:
            sections.append("\n\n".join(buf))
            buf = [para]
        else:
            buf.append(para)
    if buf:
        sections.append("\n\n".join(buf))

    if len(sections) <= 1:
        header_sections = [s.strip() for s in re.split(r"\n(?=#{1,3}\s)", text) if s.strip()]
        if len(header_sections) > 1:
            sections = header_sections

    if not sections:
        sections = [text]

    chunks: list[dict] = []
    for index, section in enumerate(sections):
        section = section.strip()
        if len(section) < min_chars and chunk_type == "patient":
            continue
        for start in range(0, len(section), max_chars):
            part = section[start : start + max_chars].strip()
            if len(part) < min_chars and chunk_type == "patient":
                continue
            title_line = _chunk_title(part, stem, start)
            chunks.append(
                {
                    "id": f"{Path(filename).stem}-{index}-{start}",
                    "chunk_type": chunk_type,
                    "title": title_line,
                    "text": part,
                    "source_file": filename,
                }
            )
    return chunks


def _chunk_title(part: str, file_stem: str, offset: int) -> str:
    for line in part.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if len(cleaned) >= 12 and not cleaned.isupper():
            return f"{file_stem}: {cleaned[:80]}"
        if len(cleaned) >= 8:
            return f"{file_stem}: {cleaned[:80]}"
    preview = re.sub(r"\s+", " ", part).strip()[:80]
    suffix = f" (part {offset // 1200 + 1})" if offset else ""
    return f"{file_stem}{suffix}: {preview or 'Patient chart'}"


async def _compact_chunk(chunk: dict) -> CompactPack:
    from .llm import converse_text

    text = chunk["text"]
    summary = _truncate(text)
    raw = await asyncio.to_thread(
        converse_text,
        "Compress clinical text into a dense summary (max 800 chars).\n\n" + text[:6000],
        max_tokens=400,
        temperature=0.2,
    )
    if raw:
        summary = _truncate(raw)

    return CompactPack(
        id=str(chunk["id"]),
        title=str(chunk.get("title", "Context")),
        summary=summary,
        text=text,
        chunk_type=str(chunk.get("chunk_type", "patient")),
        source=str(chunk.get("source_file", "upload")),
    )


def _truncate(text: str, limit: int = 800) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _knee_corpus_cache_path() -> Path:
    configured = os.environ.get("KNEE_CORPUS_CACHE", "").strip()
    if configured:
        return Path(configured)
    return _REPO_ROOT / "backend" / "assets" / "reference" / "knee_corpus_compact.json"


def _knee_chapters_dir() -> Path:
    configured = os.environ.get("KNEE_CHAPTERS_DIR", "").strip()
    if configured:
        return Path(configured)
    return _REPO_ROOT / "backend" / "assets" / "reference" / "knee_chapters"


def _reference_relevance(pack: CompactPack, procedure: str) -> float:
    terms = set(re.findall(r"[a-z0-9]+", procedure.lower()))
    terms.update({"knee", "tka", "arthroplasty", "patella", "ligament"})
    haystack = f"{pack.title} {pack.summary} {pack.source} {pack.text[:400]}".lower()
    score = sum(2.5 for term in terms if term in haystack)
    if pack.chunk_type == "sop":
        score += 4.0
    if pack.metadata.get("corpus") == "knee_chapters":
        score += 0.5
    return score


def _compact_pack_from_dict(item: dict) -> CompactPack:
    return CompactPack(
        id=str(item["id"]),
        title=str(item.get("title", "Reference")),
        summary=str(item.get("summary", "")),
        text=str(item.get("text", "")),
        chunk_type=str(item.get("chunk_type", "paper")),
        source=str(item.get("source", "knee_corpus")),
        procedure_step=item.get("procedure_step"),
        metadata=dict(item.get("metadata") or {}),
    )


def _load_knee_reference_packs(procedure: str) -> list[CompactPack]:
    cache_path = _knee_corpus_cache_path()
    if cache_path.is_file():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            packs = [_compact_pack_from_dict(item) for item in raw.get("packs", []) if isinstance(item, dict)]
            if packs:
                packs.sort(key=lambda p: (-_reference_relevance(p, procedure), p.title))
                return packs[:_MAX_REFERENCE_PACKS]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load knee corpus cache %s: %s", cache_path, exc)

    chapters_dir = _knee_chapters_dir()
    if not chapters_dir.is_dir():
        logger.warning("No knee reference corpus found (checked %s)", cache_path)
        return []

    packs: list[CompactPack] = []
    for path in sorted(chapters_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for index, section in enumerate(re.split(r"\n(?=#{1,3}\s)", text)):
            section = section.strip()
            if len(section) < 80:
                continue
            title = section.split("\n", 1)[0].lstrip("# ").strip()[:80]
            packs.append(
                CompactPack(
                    id=f"ref-{path.stem}-{index}",
                    title=title or path.stem,
                    summary=_truncate(section),
                    text=section[:4000],
                    chunk_type="sop",
                    source=path.name,
                )
            )
    packs.sort(key=lambda p: (-_reference_relevance(p, procedure), p.title))
    return packs[:_MAX_REFERENCE_PACKS]


def _build_context_window(packs: list[CompactPack], procedure: str) -> dict:
    budget = int(os.environ.get("CONTEXT_WINDOW_CHAR_BUDGET", "20000"))
    patient_reserve = int(os.environ.get("PATIENT_CONTEXT_BUDGET", str(budget // 2)))
    patient = [p for p in packs if p.chunk_type in {"patient", "manual", "comorbidity"}]
    reference = [p for p in packs if p.chunk_type not in {"patient", "manual", "comorbidity", "sop"}]
    sop = [p for p in packs if p.chunk_type == "sop"]
    patient.sort(key=lambda p: (p.id == "case-intake", p.title))
    reference.sort(key=lambda p: (-_reference_relevance(p, procedure), p.title))
    sop.sort(key=lambda p: (-_reference_relevance(p, procedure), p.title))

    header = (
        f"Surgical context window for {procedure}. "
        "Patient chart and uploaded documents first; reference corpus fills remaining budget."
    )
    lines = [header]
    used = len(header) + 1
    included_patient = 0
    included_reference = 0

    def _pack_block(pack: CompactPack) -> str:
        body = pack.summary.strip() or pack.text[:900].strip()
        source = f" [{pack.source}]" if pack.source and pack.source not in {"case-form", "upload"} else ""
        return f"• [{pack.chunk_type}] {pack.title}{source}: {body}\n"

    patient_used = 0
    for pack in patient:
        block = _pack_block(pack)
        if patient_used + len(block) > patient_reserve and included_patient > 0:
            break
        if used + len(block) > budget:
            break
        lines.append(block.rstrip())
        used += len(block)
        patient_used += len(block)
        included_patient += 1

    for pack in sop + reference:
        block = _pack_block(pack)
        if used + len(block) > budget:
            break
        lines.append(block.rstrip())
        used += len(block)
        included_reference += 1

    prompt_block = "\n".join(lines).strip()
    return {
        "char_budget": budget,
        "char_used": len(prompt_block),
        "patient_pack_count": included_patient,
        "reference_pack_count": included_reference,
        "prompt_block": prompt_block,
    }


async def regenerate_case_checklist(store: CaseStore, case_id: str) -> dict:
    """Regenerate operative milestones from case context (Nebius + SOP reference)."""
    meta = store.get_metadata(case_id)
    raw_packs = store.read_json(case_id, "compact_context.json")
    packs = [_compact_pack_from_dict(item) for item in raw_packs if isinstance(item, dict)]
    patient_packs = [p for p in packs if p.chunk_type in {"patient", "manual"}]
    if not patient_packs:
        raise ValueError(
            "Upload and parse the patient chart before generating milestones — no compact patient context yet."
        )
    reference_packs = [p for p in packs if p not in patient_packs]
    if not reference_packs:
        reference_packs = _load_knee_reference_packs(meta.procedure)

    window_path = store.case_dir(case_id) / "context_window.json"
    context_block = ""
    if window_path.exists():
        window = json.loads(window_path.read_text(encoding="utf-8"))
        context_block = str(window.get("prompt_block") or "")

    sop_packs = [p for p in reference_packs if p.chunk_type == "sop"] or reference_packs[:8]
    case_intake = {
        "patient_id": meta.patient_id,
        "procedure": meta.procedure,
        "comorbidities": ", ".join(meta.comorbidities) or "None",
        "notes": meta.manual_notes or "",
    }
    checklist = await generate_checklist(
        meta.procedure,
        patient_packs,
        sop_packs,
        context_block=context_block,
        case_intake=case_intake,
    )
    store.write_json(case_id, "checklist.json", checklist)
    return checklist


def _build_snippets(packs: list[CompactPack], patient_id: str) -> list[Snippet]:
    date = datetime.now(UTC).date().isoformat()
    snippets: list[Snippet] = []
    for pack in packs:
        source = f"{pack.chunk_type}/{pack.id}"
        is_patient = pack.chunk_type in {"patient", "manual", "comorbidity"}
        citation = pack.source if is_patient and pack.source not in {"case-form", "upload"} else source
        snippets.append(
            Snippet(
                source=source,
                text=pack.text.strip() or pack.summary,
                score=1.2 if is_patient else 1.0,
                title=pack.title,
                chunk_id=pack.id,
                doc_type=pack.chunk_type,
                guideline_ref=citation if is_patient else source,
                date=date,
            )
        )
    return snippets
