from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class IngestionStage(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    PARSING = "parsing"
    COMPACTING = "compacting"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


@dataclass
class ComplicationRecord:
    description: str
    timestamp: float
    resolved: bool = False
    resolved_at: float | None = None
    sources: list[str] = field(default_factory=list)


@dataclass
class SessionLog:
    complications: list[ComplicationRecord] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    mode_transitions: list[dict[str, Any]] = field(default_factory=list)
    closed_at: float | None = None
    operative_summary: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None


@dataclass
class CaseMetadata:
    case_id: str
    patient_id: str
    procedure: str
    manual_notes: str = ""
    comorbidities: list[str] = field(default_factory=list)
    stage: IngestionStage = IngestionStage.CREATED
    error: str | None = None
    documents: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stage"] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseMetadata:
        return cls(
            case_id=data["case_id"],
            patient_id=data["patient_id"],
            procedure=data["procedure"],
            manual_notes=data.get("manual_notes", ""),
            comorbidities=data.get("comorbidities", []),
            stage=IngestionStage(data.get("stage", IngestionStage.CREATED.value)),
            error=data.get("error"),
            documents=data.get("documents", []),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        )


def case_data_root() -> Path:
    from shared.paths import CASES_DIR

    return Path(os.environ.get("CASE_DATA_DIR", str(CASES_DIR)))


class CaseStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or case_data_root()

    def create_case(
        self,
        *,
        patient_id: str,
        procedure: str,
        manual_notes: str = "",
        comorbidities: list[str] | None = None,
    ) -> CaseMetadata:
        case_id = f"case-{uuid.uuid4().hex[:12]}"
        meta = CaseMetadata(
            case_id=case_id,
            patient_id=patient_id,
            procedure=procedure,
            manual_notes=manual_notes,
            comorbidities=comorbidities or [],
        )
        self._write_metadata(meta)
        (self.case_dir(case_id) / "raw").mkdir(parents=True, exist_ok=True)
        return meta

    def case_dir(self, case_id: str) -> Path:
        return self.root / case_id

    def get_metadata(self, case_id: str) -> CaseMetadata:
        path = self.case_dir(case_id) / "metadata.json"
        if not path.exists():
            raise FileNotFoundError(f"Case not found: {case_id}")
        return CaseMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def update_stage(self, case_id: str, stage: IngestionStage, error: str | None = None) -> CaseMetadata:
        meta = self.get_metadata(case_id)
        meta.stage = stage
        meta.error = error
        meta.updated_at = datetime.now(UTC).isoformat()
        self._write_metadata(meta)
        return meta

    def set_single_document(self, case_id: str, filename: str) -> CaseMetadata:
        meta = self.get_metadata(case_id)
        raw_dir = self.case_dir(case_id) / "raw"
        for old_name in meta.documents:
            if old_name != filename and (raw_dir / old_name).exists():
                (raw_dir / old_name).unlink()
        meta.documents = [filename]
        meta.updated_at = datetime.now(UTC).isoformat()
        self._write_metadata(meta)
        return meta

    def update_case_details(
        self,
        case_id: str,
        *,
        patient_id: str,
        procedure: str,
        manual_notes: str = "",
        comorbidities: list[str] | None = None,
    ) -> CaseMetadata:
        meta = self.get_metadata(case_id)
        meta.patient_id = patient_id
        meta.procedure = procedure
        meta.manual_notes = manual_notes
        meta.comorbidities = comorbidities or []
        meta.updated_at = datetime.now(UTC).isoformat()
        self._write_metadata(meta)
        return meta

    def write_json(self, case_id: str, name: str, payload: Any) -> Path:
        path = self.case_dir(case_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def read_json(self, case_id: str, name: str) -> Any:
        return json.loads((self.case_dir(case_id) / name).read_text(encoding="utf-8"))

    def session_log(self, case_id: str) -> SessionLog:
        path = self.case_dir(case_id) / "session_log.json"
        if not path.exists():
            return SessionLog()
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionLog(
            complications=[ComplicationRecord(**c) for c in data.get("complications", [])],
            completed_steps=data.get("completed_steps", []),
            mode_transitions=data.get("mode_transitions", []),
            closed_at=data.get("closed_at"),
            operative_summary=data.get("operative_summary"),
            events=data.get("events", []),
            transcript=data.get("transcript", []),
        )

    def save_session_log(self, case_id: str, log: SessionLog) -> None:
        self.write_json(case_id, "session_log.json", log.to_dict())

    def list_cases(self) -> list[CaseMetadata]:
        if not self.root.exists():
            return []
        cases = [
            self.get_metadata(child.name)
            for child in self.root.iterdir()
            if child.is_dir() and (child / "metadata.json").exists()
        ]
        return sorted(cases, key=lambda c: c.created_at, reverse=True)

    def delete_case(self, case_id: str) -> None:
        path = self.root / case_id
        if not path.is_dir():
            raise FileNotFoundError(f"Case not found: {case_id}")
        shutil.rmtree(path)

    def _write_metadata(self, meta: CaseMetadata) -> None:
        self.case_dir(meta.case_id).mkdir(parents=True, exist_ok=True)
        (self.case_dir(meta.case_id) / "metadata.json").write_text(
            json.dumps(meta.to_dict(), indent=2), encoding="utf-8"
        )


def build_case_status(store: CaseStore, case_id: str) -> dict[str, Any]:
    meta = store.get_metadata(case_id)
    case_dir = store.case_dir(case_id)
    preview: dict[str, Any] | None = None
    has_checklist = (case_dir / "checklist.json").exists()
    has_context = (case_dir / "compact_context.json").exists()
    show_preview = meta.stage in (IngestionStage.INDEXING, IngestionStage.READY) or has_checklist

    if show_preview:
        preview = {}
        if has_checklist:
            preview["checklist"] = store.read_json(case_id, "checklist.json")
        if meta.stage == IngestionStage.READY:
            preview["compact_context"] = store.read_json(case_id, "compact_context.json") if has_context else []
            window_path = case_dir / "context_window.json"
            preview["context_window"] = store.read_json(case_id, "context_window.json") if window_path.exists() else None
        elif has_context:
            preview["compact_context"] = store.read_json(case_id, "compact_context.json")

    return {"case": meta.to_dict(), "preview": preview}


class CaseEventHub:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, case_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[case_id].add(queue)
        return queue

    def unsubscribe(self, case_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues[case_id].discard(queue)

    def publish(self, case_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._queues.get(case_id, ())):
            try:
                queue.put_nowait(payload)
            except Exception:
                pass


class EventedCaseStore(CaseStore):
    def __init__(self, root: Path | None = None, *, on_change: Callable[[str], None] | None = None) -> None:
        super().__init__(root)
        self._on_change = on_change

    def _notify(self, case_id: str) -> None:
        if self._on_change:
            self._on_change(case_id)

    def update_stage(self, case_id: str, stage: IngestionStage, error: str | None = None) -> CaseMetadata:
        meta = super().update_stage(case_id, stage, error)
        self._notify(case_id)
        return meta

    def update_case_details(
        self,
        case_id: str,
        *,
        patient_id: str,
        procedure: str,
        manual_notes: str = "",
        comorbidities: list[str] | None = None,
    ) -> CaseMetadata:
        meta = super().update_case_details(
            case_id,
            patient_id=patient_id,
            procedure=procedure,
            manual_notes=manual_notes,
            comorbidities=comorbidities,
        )
        self._notify(case_id)
        return meta


def sse_encode(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
