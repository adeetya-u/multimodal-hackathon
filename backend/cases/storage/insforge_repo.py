"""Insforge-backed case repository (Supabase-compatible REST API)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ..store import (
    CaseMetadata,
    CaseStore,
    ComplicationRecord,
    IngestionStage,
    SessionLog,
    case_data_root,
)

_logger = logging.getLogger(__name__)


def _insforge_config() -> tuple[str, str]:
    url = os.environ.get("INSFORGE_URL", "").strip().rstrip("/")
    key = os.environ.get("INSFORGE_SERVICE_KEY", "").strip() or os.environ.get(
        "INSFORGE_ANON_KEY", ""
    ).strip()
    if not url or not key:
        raise ValueError("INSFORGE_URL and INSFORGE_SERVICE_KEY must be set")
    return url, key


def _headers(*, upsert: bool = False) -> dict[str, str]:
    _, key = _insforge_config()
    prefer = "resolution=merge-duplicates,return=representation" if upsert else "return=representation"
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _rest(path: str, method: str = "GET", *, json_body: Any = None, params: dict | None = None, upsert: bool = False) -> Any:
    base, _ = _insforge_config()
    url = f"{base}/api/database/records/{path.lstrip('/')}"
    with httpx.Client(timeout=30.0) as client:
        response = client.request(method, url, headers=_headers(upsert=upsert), json=json_body, params=params)
        if response.status_code >= 400:
            raise RuntimeError(f"Insforge {method} {path}: {response.status_code} {response.text[:200]}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


class InsforgeCaseStore(CaseStore):
    """Drop-in replacement for filesystem CaseStore using Insforge Postgres."""

    def __init__(self, root: Path | None = None) -> None:
        # Local cache for raw file bytes during ingestion
        self._local_root = root or case_data_root()
        self._local_root.mkdir(parents=True, exist_ok=True)

    def case_dir(self, case_id: str) -> Path:
        path = self._local_root / case_id
        path.mkdir(parents=True, exist_ok=True)
        return path

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
        row = {
            "case_id": case_id,
            "patient_id": patient_id,
            "procedure": procedure,
            "manual_notes": manual_notes,
            "comorbidities": comorbidities or [],
            "stage": meta.stage.value,
            "documents": [],
        }
        _rest("cases", "POST", json_body=row)
        (self.case_dir(case_id) / "raw").mkdir(parents=True, exist_ok=True)
        return meta

    def get_metadata(self, case_id: str) -> CaseMetadata:
        rows = _rest("cases", params={"case_id": f"eq.{case_id}", "select": "*"})
        if not rows:
            raise FileNotFoundError(f"Case not found: {case_id}")
        return self._meta_from_row(rows[0])

    def list_cases(self) -> list[CaseMetadata]:
        rows = _rest("cases", params={"select": "*", "order": "created_at.desc"})
        return [self._meta_from_row(r) for r in (rows or [])]

    def _write_metadata(self, meta: CaseMetadata) -> None:
        meta.updated_at = datetime.now(UTC).isoformat()
        row = {
            "patient_id": meta.patient_id,
            "procedure": meta.procedure,
            "manual_notes": meta.manual_notes,
            "comorbidities": meta.comorbidities,
            "stage": meta.stage.value,
            "error": meta.error,
            "documents": meta.documents,
            "updated_at": meta.updated_at,
        }
        _rest(f"cases?case_id=eq.{meta.case_id}", "PATCH", json_body=row)

    def update_stage(self, case_id: str, stage: IngestionStage, error: str | None = None) -> CaseMetadata:
        meta = self.get_metadata(case_id)
        meta.stage = stage
        meta.error = error
        self._write_metadata(meta)
        return meta

    def set_single_document(self, case_id: str, filename: str) -> CaseMetadata:
        meta = self.get_metadata(case_id)
        raw_dir = self.case_dir(case_id) / "raw"
        for old_name in meta.documents:
            if old_name != filename and (raw_dir / old_name).exists():
                (raw_dir / old_name).unlink()
        meta.documents = [filename]
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
        self._write_metadata(meta)
        return meta

    def write_json(self, case_id: str, name: str, payload: Any) -> Path:
        if name == "checklist.json":
            _rest(
                "checklists",
                "POST",
                json_body={"case_id": case_id, "payload": payload},
                params={"on_conflict": "case_id"},
                upsert=True,
            )
        elif name == "session_log.json":
            _rest(
                "session_logs",
                "POST",
                json_body={"case_id": case_id, "payload": payload},
                params={"on_conflict": "case_id"},
                upsert=True,
            )
        elif name == "compact_context.json":
            _rest(
                "compact_context",
                "POST",
                json_body={"case_id": case_id, "payload": payload},
                params={"on_conflict": "case_id"},
                upsert=True,
            )
        elif name == "moss_snippets.json" and isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                _rest(
                    "snippets",
                    "POST",
                    json_body={
                        "case_id": case_id,
                        "chunk_id": str(item.get("id") or item.get("chunk_id") or uuid.uuid4().hex[:8]),
                        "text": str(item.get("text") or item.get("content") or ""),
                        "metadata": item,
                    },
                    params={"on_conflict": "case_id,chunk_id"},
                    upsert=True,
                )
        # Always mirror to local path for pipeline code that reads files
        path = self.case_dir(case_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def read_json(self, case_id: str, name: str) -> Any:
        if name == "checklist.json":
            rows = _rest("checklists", params={"case_id": f"eq.{case_id}", "select": "payload"})
            if rows:
                return rows[0]["payload"]
        elif name == "session_log.json":
            rows = _rest("session_logs", params={"case_id": f"eq.{case_id}", "select": "payload"})
            if rows:
                return rows[0]["payload"]
        elif name == "compact_context.json":
            rows = _rest("compact_context", params={"case_id": f"eq.{case_id}", "select": "payload"})
            if rows:
                return rows[0]["payload"]
        elif name == "moss_snippets.json":
            rows = _rest("snippets", params={"case_id": f"eq.{case_id}", "select": "metadata"})
            if rows:
                return [r["metadata"] for r in rows]
        path = self.case_dir(case_id) / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"{name} not found for {case_id}")

    def session_log(self, case_id: str) -> SessionLog:
        try:
            data = self.read_json(case_id, "session_log.json")
        except FileNotFoundError:
            return SessionLog()
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

    def delete_case(self, case_id: str) -> None:
        self.get_metadata(case_id)
        _rest(f"cases?case_id=eq.{case_id}", "DELETE")
        local = self._local_root / case_id
        if local.exists():
            shutil.rmtree(local)

    @staticmethod
    def _meta_from_row(row: dict) -> CaseMetadata:
        return CaseMetadata(
            case_id=row["case_id"],
            patient_id=row["patient_id"],
            procedure=row.get("procedure", "Surgery"),
            manual_notes=row.get("manual_notes", ""),
            comorbidities=row.get("comorbidities") or [],
            stage=IngestionStage(row.get("stage", IngestionStage.CREATED.value)),
            error=row.get("error"),
            documents=row.get("documents") or [],
            created_at=row.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=row.get("updated_at", datetime.now(UTC).isoformat()),
        )
