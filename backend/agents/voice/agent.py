"""Deepagent for the Doctor Voice Agent (used during live surgery)."""

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import create_summarization_tool_middleware
from langchain_aws import ChatBedrockConverse
from langchain_aws.middleware.prompt_caching import BedrockPromptCachingMiddleware
from langchain_core.tools import tool

from shared.secrets import secrets
from agents.voice.tools import (
    search_patient_context as _search_patient_context,
    mark_step_complete as _mark_step_complete,
    get_procedure_steps as _get_procedure_steps,
    log_conversation as _log_conversation,
)

from shared.paths import PATIENTS_DIR

DOCTOR_SYSTEM_PROMPT = (
    "You are Scalpel, a surgical voice AI assistant for live surgery. "
    "You help surgeons with real-time clinical questions during operations.\n\n"
    "TOOLS:\n"
    "- search_patient_context: Search the patient's indexed surgical context (guidelines, textbook extracts). Use this for any medical question.\n"
    "- mark_step_complete: When the doctor says a step is done, mark it complete. Match their words to the closest step number.\n"
    "- get_procedure_steps: Check which steps are pending/done.\n"
    "- log_entry: Log important Q&A or events. ALWAYS call this in parallel with other tools, never alone blocking the response.\n\n"
    "RULES:\n"
    "- Keep responses concise and voice-friendly. No markdown, no bullet points, no special characters.\n"
    "- For medical questions: search patient context.\n"
    "- When doctor says 'step done' or 'completed step X' or similar, call mark_step_complete.\n"
    "- ALWAYS call log_entry in PARALLEL with your other tool calls (e.g. call mark_step_complete AND log_entry together). Never call log_entry alone as a separate turn.\n"
    "- If you cannot find the answer, say so honestly."
)


def _load_patient_context(patient_id: str) -> str:
    """Load patient info and procedure steps into a context string for the system prompt."""
    if not patient_id:
        return ""

    parts = []

    info_path = PATIENTS_DIR / patient_id / "info.json"
    if info_path.exists():
        with open(info_path) as f:
            info = json.load(f)
        parts.append(
            f"PATIENT: {info.get('name', 'Unknown')}, {info.get('age', '?')}y {info.get('gender', '')}\n"
            f"Surgery: {info.get('surgery_type', 'Unknown')}\n"
            f"Medical History: {info.get('medical_history', 'None')}\n"
            f"Allergies: {info.get('allergies', 'None')}\n"
            f"Medications: {info.get('medications', 'None')}\n"
            f"Notes: {info.get('notes', '')}"
        )

    steps_path = PATIENTS_DIR / patient_id / "context" / "procedure_steps.json"
    if steps_path.exists():
        with open(steps_path) as f:
            data = json.load(f)
        step_lines = [f"PROCEDURE: {data.get('procedure_name', 'Unknown')}"]
        for step in data.get("steps", []):
            step_lines.append(f"  Step {step.get('step_number')}: {step.get('title')}")
        parts.append("\n".join(step_lines))

    return "\n\n".join(parts)


def create_doctor_agent(patient_id: str = ""):
    """Create a doctor agent with tools bound to the given patient_id."""
    from botocore.config import Config as BotoConfig

    patient_context = _load_patient_context(patient_id)
    system_prompt = DOCTOR_SYSTEM_PROMPT
    if patient_context:
        system_prompt += f"\n\n--- CURRENT PATIENT ---\n{patient_context}\n--- END ---"

    llm = ChatBedrockConverse(
        model="us.anthropic.claude-sonnet-4-6",
        region_name=os.environ.get("AWS_BEDROCK_REGION", secrets.get("AWS_BEDROCK_REGION", "us-east-1")),
        aws_access_key_id=os.environ.get("BEDROCK_AWS_ACCESS_KEY_ID", secrets.get("BEDROCK_AWS_ACCESS_KEY_ID", "")),
        aws_secret_access_key=os.environ.get("BEDROCK_AWS_SECRET_ACCESS_KEY", secrets.get("BEDROCK_AWS_SECRET_ACCESS_KEY", "")),
        temperature=0.3,
        max_tokens=1024,
        config=BotoConfig(read_timeout=60),
    )

    @tool
    async def search_patient_context(query: Annotated[str, "Search query about the procedure or patient"]) -> str:
        """Search the patient's indexed surgical context (guidelines, textbook extracts, procedure info) for relevant information."""
        return await _search_patient_context.ainvoke({"patient_id": patient_id, "query": query})

    @tool
    async def mark_step_complete(step_number: Annotated[int, "Step number to mark as complete"]) -> str:
        """Mark a procedural step as completed when the doctor says it's done."""
        return await _mark_step_complete.ainvoke({"patient_id": patient_id, "step_number": step_number})

    @tool
    async def get_steps() -> str:
        """Get the current procedure steps and their completion status."""
        return await _get_procedure_steps.ainvoke({"patient_id": patient_id})

    @tool
    async def log_entry(entry: Annotated[str, "Conversation entry to log"]) -> str:
        """Log a conversation entry. This is fire-and-forget — call in parallel with other tools, never alone."""
        asyncio.create_task(_log_conversation.ainvoke({"patient_id": patient_id, "entry": entry}))
        return "Logged."

    return create_deep_agent(
        model=llm,
        tools=[
            search_patient_context,
            mark_step_complete,
            get_steps,
            log_entry,
        ],
        system_prompt=system_prompt,
        middleware=[
            create_summarization_tool_middleware(llm, StateBackend()),
            BedrockPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        ],
    )


# Default instance for import (used when patient_id not yet known)
doctor_agent = create_doctor_agent()
