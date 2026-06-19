"""Patient context tools — save procedure steps, guidelines PDFs, and textbook extracts."""

import json
import os
from pathlib import Path
from typing import Annotated

import httpx
from langchain_core.tools import tool

from shared.paths import PATIENTS_DIR


def _get_patient_dir(patient_id: str) -> Path:
    patient_dir = PATIENTS_DIR / patient_id
    if not patient_dir.exists():
        raise ValueError(f"Patient {patient_id} not found")
    return patient_dir


@tool
async def save_procedure_steps(
    patient_id: Annotated[str, "Patient ID to save steps for"],
    procedure_name: Annotated[str, "Name of the surgical procedure"],
    steps: Annotated[list, "List of steps. Each step: {step_number, title, description}"] = None,
) -> str:
    """Save procedure steps JSON. Keep it minimal — just step_number, title, and a one-line description per step. 8-12 steps max."""
    if not steps:
        return "Error: 'steps' required. List of {step_number, title, description}."

    try:
        patient_dir = _get_patient_dir(patient_id)
    except ValueError as e:
        return str(e)

    context_dir = patient_dir / "context"
    context_dir.mkdir(exist_ok=True)

    procedure_data = {
        "procedure_name": procedure_name,
        "patient_id": patient_id,
        "total_steps": len(steps),
        "steps": steps,
    }

    output_path = context_dir / "procedure_steps.json"
    with open(output_path, "w") as f:
        json.dump(procedure_data, f, indent=2)

    return f"Saved {len(steps)} procedure steps to {output_path.relative_to(PATIENTS_DIR)}"


@tool
async def save_context_file(
    patient_id: Annotated[str, "Patient ID"],
    filename: Annotated[str, "Filename to save (e.g. 'guidelines_tka.md', 'drug_interactions.md')"],
    content: Annotated[str, "Content to save — can be guidelines text, extracted web content, or synthesized notes"],
    category: Annotated[str, "Category: 'guidelines', 'evidence', 'protocols', 'notes'"] = "guidelines",
) -> str:
    """Save a context file to the patient's context folder.

    Use this to store:
    - Extracted surgical guidelines relevant to this procedure
    - Drug interaction data specific to patient's medications
    - Anaesthesia protocols based on patient comorbidities
    - Evidence summaries from textbooks/web searches
    - Any synthesized clinical notes for intra-operative reference

    Files are organized by category subfolder within context/.
    """
    try:
        patient_dir = _get_patient_dir(patient_id)
    except ValueError as e:
        return str(e)

    safe_filename = filename.replace("/", "_").replace("\\", "_").replace("..", "")
    category_dir = patient_dir / "context" / category
    category_dir.mkdir(parents=True, exist_ok=True)

    output_path = category_dir / safe_filename
    with open(output_path, "w") as f:
        f.write(content)

    return f"Saved {len(content)} chars to {output_path.relative_to(PATIENTS_DIR)}"


@tool
async def read_patient_info(
    patient_id: Annotated[str, "Patient ID to read info for"],
) -> str:
    """Read the patient's info.json file to get their details, medical history, allergies, medications, and uploaded documents.

    Always call this first to understand the patient before researching procedure steps.
    """
    try:
        patient_dir = _get_patient_dir(patient_id)
    except ValueError as e:
        return str(e)

    info_path = patient_dir / "info.json"
    if not info_path.exists():
        return "Patient info.json not found"

    with open(info_path) as f:
        info = json.load(f)

    lines = [
        f"Patient: {info.get('name', 'Unknown')}",
        f"Age: {info.get('age', 'N/A')} | Gender: {info.get('gender', 'N/A')}",
        f"Surgery: {info.get('surgery_type', 'N/A')}",
        f"Medical History: {info.get('medical_history', 'None')}",
        f"Allergies: {info.get('allergies', 'None')}",
        f"Medications: {info.get('medications', 'None')}",
        f"Notes: {info.get('notes', 'None')}",
        f"Uploaded Files: {', '.join(info.get('files', [])) or 'None'}",
    ]
    return "\n".join(lines)


@tool
async def list_patient_context(
    patient_id: Annotated[str, "Patient ID"],
) -> str:
    """List all files in the patient's context folder to see what has already been saved."""
    try:
        patient_dir = _get_patient_dir(patient_id)
    except ValueError as e:
        return str(e)

    context_dir = patient_dir / "context"
    if not context_dir.exists():
        return "No context folder yet. Use save_context_file or save_procedure_steps to create content."

    files = []
    for p in sorted(context_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(context_dir)
            size = p.stat().st_size
            files.append(f"  {rel} ({size} bytes)")

    if not files:
        return "Context folder is empty."

    return f"Context files ({len(files)}):\n" + "\n".join(files)


@tool
async def download_guideline_pdf(
    patient_id: Annotated[str, "Patient ID"],
    url: Annotated[str, "URL of the PDF to download"],
    filename: Annotated[str, "Filename for the PDF (e.g. 'NICE_TKA_guidelines_2023.pdf')"],
    title: Annotated[str, "Title/description of the guideline"],
    source: Annotated[str, "Source organization (e.g. 'NICE', 'AAOS', 'ASA', 'ERAS')"],
) -> str:
    """Download a guideline PDF and save it to the patient's context/guidelines/ folder.

    Use this when you find guideline PDFs from web_search results. Store the actual PDF
    so the surgeon can reference it during or after surgery.

    Also creates a metadata sidecar file (.meta.json) with source info.
    """
    try:
        patient_dir = _get_patient_dir(patient_id)
    except ValueError as e:
        return str(e)

    guidelines_dir = patient_dir / "context" / "guidelines"
    guidelines_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = filename.replace("/", "_").replace("\\", "_").replace("..", "")
    if not safe_filename.endswith(".pdf"):
        safe_filename += ".pdf"

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if "pdf" not in content_type and not r.content[:5] == b"%PDF-":
                return f"URL did not return a PDF (content-type: {content_type}). Use web_extract instead for HTML content."

            pdf_path = guidelines_dir / safe_filename
            with open(pdf_path, "wb") as f:
                f.write(r.content)
    except Exception as e:
        return f"Download failed: {e}"

    meta = {
        "title": title,
        "source": source,
        "url": url,
        "filename": safe_filename,
        "size_bytes": len(r.content),
    }
    meta_path = guidelines_dir / f"{safe_filename}.meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return f"Downloaded {safe_filename} ({len(r.content) // 1024} KB) from {source}. Saved to context/guidelines/"


@tool
async def save_textbook_extract(
    patient_id: Annotated[str, "Patient ID"],
    book_title: Annotated[str, "Full title of the textbook"],
    book_isbn: Annotated[str, "ISBN of the textbook"],
    speciality: Annotated[str, "Medical speciality (e.g. 'Orthopaedics', 'Anaesthesia')"],
    sections: Annotated[list[dict], "List of extracted sections. Each: {heading, content, block_file_path, relevance}"],
    summary: Annotated[str, "Brief summary of why this textbook content is relevant to the patient's surgery"],
) -> str:
    """Save textbook extracts as a structured markdown file in the patient's context.

    After using query_library_db + read_textbook_file to find relevant content,
    use this tool to save a well-organized markdown file with:
    - Book metadata (title, ISBN, speciality)
    - Why it's relevant to this patient
    - Extracted sections with headings and content

    This creates a markdown file in context/textbooks/ named after the book.
    The surgeon can reference these during surgery for detailed procedure guidance.
    """
    try:
        patient_dir = _get_patient_dir(patient_id)
    except ValueError as e:
        return str(e)

    textbooks_dir = patient_dir / "context" / "textbooks"
    textbooks_dir.mkdir(parents=True, exist_ok=True)

    safe_name = book_isbn.replace("/", "_").replace(" ", "_")
    filename = f"{safe_name}_{speciality.lower().replace(' ', '_')}.md"

    lines = [
        f"# {book_title}",
        f"",
        f"**ISBN:** {book_isbn}",
        f"**Speciality:** {speciality}",
        f"**Relevance:** {summary}",
        f"",
        f"---",
        f"",
    ]

    for i, section in enumerate(sections, 1):
        heading = section.get("heading", f"Section {i}")
        content = section.get("content", "")
        source_path = section.get("block_file_path", "")
        relevance = section.get("relevance", "")

        lines.append(f"## {heading}")
        if relevance:
            lines.append(f"*Relevance: {relevance}*")
        lines.append(f"")
        lines.append(content)
        if source_path:
            lines.append(f"")
            lines.append(f"_Source: {source_path}_")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    md_content = "\n".join(lines)
    output_path = textbooks_dir / filename
    with open(output_path, "w") as f:
        f.write(md_content)

    return f"Saved textbook extract: {filename} ({len(sections)} sections, {len(md_content)} chars) to context/textbooks/"
