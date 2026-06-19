"""Patient context indexer — parses docs and creates a Moss vector index for the patient."""

import json
import os
from io import BytesIO
from pathlib import Path

import pypdf
from moss import MossClient, DocumentInfo

from shared.paths import PATIENTS_DIR
from shared.unsiloed import parse_pdf as unsiloed_parse_pdf

MOSS_PROJECT_ID = os.environ.get("MOSS_PROJECT_ID", "")
MOSS_PROJECT_KEY = os.environ.get("MOSS_PROJECT_KEY", "")

UNSILOED_API_KEY = os.environ.get("UNSILOED_API_KEY", "")


def _get_moss_client() -> MossClient:
    return MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)


def _parse_pdf_local(file_path: Path) -> list[str]:
    """Parse PDF into text chunks using pypdf (local, no API needed)."""
    reader = pypdf.PdfReader(str(file_path))
    chunks = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            chunks.append(text.strip())
    return chunks


def _parse_markdown(file_path: Path) -> list[str]:
    """Split markdown file into chunks by headings."""
    content = file_path.read_text(encoding="utf-8")
    if not content.strip():
        return []

    sections = []
    current = []

    for line in content.split("\n"):
        if line.startswith("## ") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)

    if current:
        sections.append("\n".join(current).strip())

    return [s for s in sections if len(s) > 20]


def _parse_json_steps(file_path: Path) -> list[str]:
    """Parse procedure_steps.json into per-step chunks."""
    with open(file_path) as f:
        data = json.load(f)

    chunks = []
    procedure = data.get("procedure_name", "Surgery")

    for step in data.get("steps", []):
        text = f"Step {step.get('step_number', '?')}: {step.get('title', '')}\n"
        text += f"{step.get('description', '')}\n"
        if step.get("key_considerations"):
            text += f"Considerations: {step['key_considerations']}\n"
        if step.get("instruments"):
            instruments = step["instruments"] if isinstance(step["instruments"], list) else [step["instruments"]]
            text += f"Instruments: {', '.join(instruments)}\n"
        if step.get("warnings"):
            warnings = step["warnings"] if isinstance(step["warnings"], list) else [step["warnings"]]
            text += f"Warnings: {', '.join(warnings)}\n"
        chunks.append(text.strip())

    return chunks


async def _parse_pdf_unsiloed(file_path: Path) -> list[str]:
    """Parse PDF using Unsiloed API (better quality, requires API key)."""
    if not UNSILOED_API_KEY:
        return _parse_pdf_local(file_path)

    try:
        text = await unsiloed_parse_pdf(file_path, UNSILOED_API_KEY)
        if text.strip():
            return [text]
    except Exception:
        pass

    return _parse_pdf_local(file_path)


async def index_patient_context(patient_id: str) -> dict:
    """Parse all patient context files and create a Moss index.

    Returns: {"index_name": str, "document_count": int, "chunks": int}
    """
    patient_dir = PATIENTS_DIR / patient_id
    context_dir = patient_dir / "context"
    docs_dir = patient_dir / "docs"

    if not context_dir.exists():
        raise ValueError(f"No context folder for patient {patient_id}")

    documents: list[DocumentInfo] = []
    doc_counter = 0

    # Parse uploaded patient docs (PDFs in docs/)
    if docs_dir.exists():
        for file_path in docs_dir.iterdir():
            if file_path.suffix.lower() == ".pdf":
                chunks = await _parse_pdf_unsiloed(file_path)
                for i, chunk in enumerate(chunks):
                    doc_counter += 1
                    documents.append(DocumentInfo(
                        id=f"upload-{file_path.stem}-{i}",
                        text=chunk,
                        metadata={"source": "upload", "file": file_path.name, "page": str(i + 1)},
                    ))

    # Parse context files
    for file_path in sorted(context_dir.rglob("*")):
        if not file_path.is_file():
            continue

        rel_path = str(file_path.relative_to(context_dir))

        if file_path.name == "procedure_steps.json":
            chunks = _parse_json_steps(file_path)
            category = "procedure"
        elif file_path.suffix == ".pdf":
            chunks = await _parse_pdf_unsiloed(file_path)
            category = "guidelines"
        elif file_path.suffix == ".md":
            chunks = _parse_markdown(file_path)
            category = rel_path.split("/")[0] if "/" in rel_path else "context"
        elif file_path.suffix == ".json" and file_path.name.endswith(".meta.json"):
            continue
        else:
            try:
                text = file_path.read_text(encoding="utf-8")
                chunks = [text] if len(text) > 20 else []
                category = "context"
            except (UnicodeDecodeError, ValueError):
                continue

        for i, chunk in enumerate(chunks):
            doc_counter += 1
            documents.append(DocumentInfo(
                id=f"{category}-{file_path.stem}-{i}",
                text=chunk,
                metadata={"source": category, "file": rel_path},
            ))

    if not documents:
        raise ValueError("No parseable content found in patient context")

    # Create Moss index
    index_name = f"patient-{patient_id}"
    client = _get_moss_client()

    try:
        await client.delete_index(index_name)
    except Exception:
        pass

    await client.create_index(index_name, documents, model_id="moss-minilm")

    return {
        "index_name": index_name,
        "document_count": len(documents),
    }
