from __future__ import annotations

import json
import re

from .checklist import ChecklistState, ChecklistStep
from .search import load_case_corpus
from .store import case_data_root
from .types import Snippet


def build_bootstrap_payload(case_id: str) -> dict:
    case_dir = case_data_root() / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case not found: {case_id}")

    from .checklist import load_case_checklist

    checklist = load_case_checklist(case_id)
    context = _load_patient_context(case_id)
    snippets = load_case_corpus(case_dir)
    return {
        "case_id": case_id,
        "checklist": checklist.to_dict(),
        "context": context,
        "snippets": [s.to_dict() for s in snippets],
    }


def bootstrap_to_gzip(payload: dict) -> bytes:
    import gzip

    return gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def bootstrap_from_gzip(data: bytes) -> dict:
    import gzip

    parsed = json.loads(gzip.decompress(data).decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("bootstrap payload must be a JSON object")
    return parsed


def case_has_local_artifacts(case_id: str | None) -> bool:
    if not case_id:
        return False
    case_dir = case_data_root() / case_id
    return case_dir.is_dir() and (case_dir / "patient_context.json").exists()


def snippets_from_bootstrap(payload: dict) -> list[Snippet]:
    raw_items = payload.get("snippets")
    if not isinstance(raw_items, list):
        return []
    return [Snippet.from_dict(item) for item in raw_items if isinstance(item, dict)]


class SurgeryContext:
    def __init__(self, *, patient_id: str, procedure: str, summary: str, raw: dict) -> None:
        self.patient_id = patient_id
        self.procedure = procedure
        self.summary = summary
        self.raw = raw


def checklist_from_bootstrap(payload: dict) -> ChecklistState | None:
    raw = payload.get("checklist")
    if not isinstance(raw, dict):
        return None
    import time

    steps = [
        ChecklistStep(
            id=str(s["id"]),
            label=str(s["label"]),
            aliases=[str(a) for a in s.get("aliases", [])],
            status=s.get("status", "pending"),
            completed_at=s.get("completed_at"),
        )
        for s in raw.get("steps", [])
        if isinstance(s, dict)
    ]
    return ChecklistState(
        procedure=str(raw.get("procedure", "Surgery")),
        mode=str(raw.get("mode", "logger")),
        steps=steps,
        updated_at=float(raw.get("updated_at") or time.time()),
    )


def context_from_bootstrap(payload: dict) -> SurgeryContext | None:
    raw = payload.get("context")
    if not isinstance(raw, dict):
        return None
    return SurgeryContext(
        patient_id=str(raw.get("patient_id", "UNKNOWN")),
        procedure=str(raw.get("procedure", "Unknown")),
        summary=_format_context(raw),
        raw=raw,
    )


def _load_patient_context(case_id: str) -> dict:
    path = case_data_root() / case_id / "patient_context.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    meta_path = case_data_root() / case_id / "metadata.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {"case_id": case_id}


def load_case_context(case_id: str | None) -> SurgeryContext:
    if case_id:
        raw = _load_patient_context(case_id)
        return SurgeryContext(
            patient_id=str(raw.get("patient_id", "UNKNOWN")),
            procedure=str(raw.get("procedure", "Unknown")),
            summary=_format_context(raw),
            raw=raw,
        )
    return SurgeryContext(
        patient_id="UNKNOWN",
        procedure="Unknown",
        summary="No patient context loaded.",
        raw={},
    )


def _format_context(raw: dict) -> str:
    nested = raw.get("context_window")
    if isinstance(nested, dict):
        block = nested.get("prompt_block", "")
        if isinstance(block, str) and block.strip():
            base = block.strip()
        else:
            base = ""
    else:
        base = ""
    parts: list[str] = []
    if base:
        parts.append(base)
    for key in ("patient_id", "procedure", "comorbidities", "notes"):
        if raw.get(key):
            parts.append(f"- {key}: {raw[key]}")
    allergy_line = _allergies_highlight(raw)
    if allergy_line:
        parts.append(f"- allergies: {allergy_line}")
    for pack in raw.get("compact_packs", [])[:5]:
        parts.append(f"- {pack.get('title', 'context')}: {pack.get('summary', '')[:200]}")
    return "\n".join(parts) if parts else "No patient context loaded."


def _allergies_highlight(raw: dict) -> str | None:
    """Surface allergy facts from chart text — never invent NKDA."""
    chunks: list[str] = []
    notes = raw.get("notes")
    if isinstance(notes, str) and notes.strip():
        chunks.append(notes)
    comorb = raw.get("comorbidities")
    if isinstance(comorb, list):
        chunks.extend(str(c) for c in comorb)
    elif isinstance(comorb, str) and comorb.strip():
        chunks.append(comorb)
    for pack in raw.get("compact_packs") or []:
        if not isinstance(pack, dict):
            continue
        chunks.append(str(pack.get("title") or ""))
        chunks.append(str(pack.get("summary") or ""))
    blob = " ".join(chunks)
    lower = blob.lower()
    if "penicillin" in lower and "allerg" in lower:
        return "Documented penicillin allergy (see chart excerpts)"
    if re.search(r"\ballerg", lower):
        for sentence in re.split(r"[.\n;]+", blob):
            if re.search(r"\ballerg", sentence, re.I):
                cleaned = sentence.strip()
                if cleaned:
                    return cleaned[:220]
    return None


class BootstrapChunkAssembler:
    def __init__(self) -> None:
        self._chunks: dict[int, bytes] = {}
        self._total = 0

    def add_chunk(self, index: int, total: int, data_b64: str) -> bool:
        import base64

        if index == 0 or (self._total and self._total != total):
            self._chunks = {}
        self._total = total
        self._chunks[index] = base64.b64decode(data_b64.encode("ascii"))
        return self.is_complete()

    def is_complete(self) -> bool:
        return self._total > 0 and len(self._chunks) == self._total

    def payload(self) -> dict:
        if not self.is_complete():
            raise ValueError("bootstrap chunks incomplete")
        ordered = b"".join(self._chunks[i] for i in range(self._total))
        return bootstrap_from_gzip(ordered)
