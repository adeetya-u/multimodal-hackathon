"""Tools for the live surgery voice agent — Moss search, step completion, conversation logging."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool
from moss import MossClient, QueryOptions

from shared.paths import PATIENTS_DIR

MOSS_PROJECT_ID = os.environ.get("MOSS_PROJECT_ID", "")
MOSS_PROJECT_KEY = os.environ.get("MOSS_PROJECT_KEY", "")


def _get_moss_client() -> MossClient:
    return MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)


@tool
async def search_patient_context(patient_id: Annotated[str, "Patient ID"], query: Annotated[str, "Search query about the procedure or patient"]) -> str:
    """Search the patient's indexed surgical context (guidelines, textbook extracts, procedure info) using semantic search. Use this when the doctor asks about the procedure, guidelines, or patient-specific info."""
    try:
        client = _get_moss_client()
        index_name = f"patient-{patient_id}"
        results = await client.query(index_name, query, QueryOptions(top_k=5, alpha=0.8))
        if not results.docs:
            return "No relevant information found in patient context."
        return "\n---\n".join(d.text for d in results.docs)
    except Exception as e:
        return f"Search failed: {e}"


@tool
async def mark_step_complete(patient_id: Annotated[str, "Patient ID"], step_number: Annotated[int, "Step number to mark as complete"]) -> str:
    """Mark a procedural step as completed. Call this when the doctor says a step is done or has been completed."""
    steps_path = PATIENTS_DIR / patient_id / "context" / "procedure_steps.json"
    if not steps_path.exists():
        return f"No procedure steps found for patient {patient_id}"

    try:
        with open(steps_path) as f:
            data = json.load(f)

        found = False
        for step in data.get("steps", []):
            if step.get("step_number") == step_number:
                step["completed"] = True
                step["completed_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break

        if not found:
            return f"Step {step_number} not found. Available steps: 1-{len(data.get('steps', []))}"

        with open(steps_path, "w") as f:
            json.dump(data, f, indent=2)

        return f"Step {step_number} marked as complete."
    except Exception as e:
        return f"Error marking step: {e}"


@tool
async def get_procedure_steps(patient_id: Annotated[str, "Patient ID"]) -> str:
    """Get the current procedure steps and their completion status. Use to check which step the surgery is on."""
    steps_path = PATIENTS_DIR / patient_id / "context" / "procedure_steps.json"
    if not steps_path.exists():
        return f"No procedure steps found for patient {patient_id}"

    with open(steps_path) as f:
        data = json.load(f)

    lines = [f"Procedure: {data.get('procedure_name', 'Unknown')}"]
    for step in data.get("steps", []):
        status = "DONE" if step.get("completed") else "PENDING"
        lines.append(f"[{status}] Step {step.get('step_number')}: {step.get('title')}")
    return "\n".join(lines)


@tool
async def log_conversation(patient_id: Annotated[str, "Patient ID"], entry: Annotated[str, "Conversation entry to log (e.g. 'Doctor asked about bleeding risk, answered with...')"]) -> str:
    """Log a conversation entry to the surgical session log. Use after answering important questions or when notable events happen during surgery."""
    log_path = PATIENTS_DIR / patient_id / "context" / "session_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": entry,
    }

    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return "Logged."
