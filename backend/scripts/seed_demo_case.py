#!/usr/bin/env python3
"""Seed demo case-001: copy Donnelly chart and run full ingestion (compact + index + checklist)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import shared.bootstrap  # noqa: F401
from shared.paths import BACKEND_ROOT

from cases.pipeline import run_ingestion_pipeline
from cases.store import CaseMetadata, CaseStore, IngestionStage, case_data_root

REPO_ROOT = BACKEND_ROOT.parent

DEMO_CASE_ID = "case-001"
DEMO_PATIENT_ID = "001"
DEMO_PROCEDURE = "Total Knee Arthroplasty, right knee"
DEMO_COMORBIDITIES = [
    "Type 2 diabetes",
    "Hypertension",
    "Obesity",
    "Chronic kidney disease stage 2-3a",
    "Obstructive sleep apnoea",
]


async def seed_demo_case_async(*, reset: bool = True) -> tuple[Path, dict]:
    root = case_data_root()
    root.mkdir(parents=True, exist_ok=True)

    if reset:
        for child in root.iterdir():
            if child.is_dir() and child.name != DEMO_CASE_ID:
                shutil.rmtree(child)

    store = CaseStore(root)
    case_dir = store.case_dir(DEMO_CASE_ID)
    raw_dir = case_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    mock_src = BACKEND_ROOT / "assets" / "demo" / "mock-patient-TKA-Donnelly.md"
    doc_name = "mock-patient-TKA-Donnelly.md"
    documents: list[str] = []
    if mock_src.is_file():
        shutil.copy2(mock_src, raw_dir / doc_name)
        documents = [doc_name]

    meta = CaseMetadata(
        case_id=DEMO_CASE_ID,
        patient_id=DEMO_PATIENT_ID,
        procedure=DEMO_PROCEDURE,
        comorbidities=DEMO_COMORBIDITIES,
        documents=documents,
        stage=IngestionStage.CREATED,
    )
    store._write_metadata(meta)

    await run_ingestion_pipeline(store, DEMO_CASE_ID)

    checklist = store.read_json(DEMO_CASE_ID, "checklist.json")
    return case_dir, checklist


def seed_demo_case(*, reset: bool = True) -> tuple[Path, dict]:
    return asyncio.run(seed_demo_case_async(reset=reset))


if __name__ == "__main__":
    path, checklist = seed_demo_case(reset=True)
    snippets_path = path / "moss_snippets.json"
    snippet_count = len(json.loads(snippets_path.read_text())) if snippets_path.exists() else 0
    context_path = path / "context_window.json"
    context_text = ""
    if context_path.exists():
        context_text = json.loads(context_path.read_text()).get("prompt_block", "")
    has_allergy = "penicillin" in context_text.lower()
    print(
        f"Seeded demo case at {path} "
        f"({len(checklist.get('steps', []))} checklist steps, "
        f"{snippet_count} snippets, allergy_in_context={has_allergy})"
    )
