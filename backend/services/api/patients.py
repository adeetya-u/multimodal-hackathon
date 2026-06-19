"""Optional patient-prep API routes (secondary to case-based surgical logger)."""

import asyncio
import json
import os
import shutil
import time
import uuid
from collections import defaultdict

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from shared.paths import PATIENTS_DIR

PATIENTS_DIR.mkdir(parents=True, exist_ok=True)
_prep_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


def register(app: FastAPI) -> None:
    @app.post("/getToken", status_code=410)
    async def get_token_legacy():
        return JSONResponse(
            status_code=410,
            content={"error": "LiveKit tokens removed — use Vapi Web SDK"},
        )

    @app.post("/api/patients", status_code=201)
    async def create_patient(
        name: str = Form(...),
        age: str = Form(...),
        gender: str = Form(...),
        surgery_type: str = Form(...),
        medical_history: str = Form(""),
        allergies: str = Form(""),
        medications: str = Form(""),
        notes: str = Form(""),
        files: list[UploadFile] = File(default=[]),
    ):
        patient_id = str(uuid.uuid4())[:8]
        patient_dir = os.path.join(PATIENTS_DIR, patient_id)
        docs_dir = os.path.join(patient_dir, "docs")
        os.makedirs(docs_dir, exist_ok=True)

        patient_info = {
            "id": patient_id,
            "name": name,
            "age": age,
            "gender": gender,
            "surgery_type": surgery_type,
            "medical_history": medical_history,
            "allergies": allergies,
            "medications": medications,
            "notes": notes,
            "files": [],
            "created_at": int(time.time()),
        }

        for file in files:
            if file.filename:
                safe_name = file.filename.replace("/", "_").replace("\\", "_")
                file_path = os.path.join(docs_dir, safe_name)
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(file.file, f)
                patient_info["files"].append(safe_name)

        with open(os.path.join(patient_dir, "info.json"), "w") as f:
            json.dump(patient_info, f, indent=2)

        asyncio.create_task(_run_prep_agent(patient_id))
        return patient_info

    @app.get("/api/patients/{patient_id}/stream")
    async def stream_prep_events(patient_id: str):
        queue: asyncio.Queue = asyncio.Queue()
        _prep_subscribers[patient_id].append(queue)

        async def event_generator():
            try:
                while True:
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {data}\n\n"
                        parsed = json.loads(data)
                        if parsed.get("type") == "status" and parsed.get("status") == "done":
                            break
                        if parsed.get("type") == "error":
                            break
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            finally:
                _prep_subscribers[patient_id].remove(queue)
                if not _prep_subscribers[patient_id]:
                    del _prep_subscribers[patient_id]

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/patients")
    async def list_patients():
        patients = []
        if not os.path.exists(PATIENTS_DIR):
            return patients
        for pid in sorted(os.listdir(PATIENTS_DIR), reverse=True):
            info_path = os.path.join(PATIENTS_DIR, pid, "info.json")
            if os.path.exists(info_path):
                with open(info_path) as f:
                    patients.append(json.load(f))
        return patients

    @app.get("/api/patients/{patient_id}")
    async def get_patient(patient_id: str):
        info_path = os.path.join(PATIENTS_DIR, patient_id, "info.json")
        if not os.path.exists(info_path):
            return JSONResponse({"error": "Patient not found"}, status_code=404)
        with open(info_path) as f:
            return json.load(f)

    @app.get("/api/patients/{patient_id}/context")
    async def get_patient_context(patient_id: str):
        context_dir = os.path.join(PATIENTS_DIR, patient_id, "context")
        if not os.path.exists(context_dir):
            return JSONResponse({"status": "pending", "files": []})

        files = []
        for root, _, filenames in os.walk(context_dir):
            for fname in sorted(filenames):
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, context_dir)
                files.append({"path": rel_path, "size": os.path.getsize(fpath)})

        steps_path = os.path.join(context_dir, "procedure_steps.json")
        has_steps = os.path.exists(steps_path)
        return {"status": "ready" if has_steps else "partial", "files": files, "has_procedure_steps": has_steps}

    @app.post("/api/patients/{patient_id}/prepare")
    async def prepare_patient(patient_id: str):
        info_path = os.path.join(PATIENTS_DIR, patient_id, "info.json")
        if not os.path.exists(info_path):
            return JSONResponse({"error": "Patient not found"}, status_code=404)
        asyncio.create_task(_run_prep_agent(patient_id))
        return {"status": "started", "patient_id": patient_id}

    @app.get("/api/patients/{patient_id}/steps")
    async def get_procedure_steps(patient_id: str):
        steps_path = os.path.join(PATIENTS_DIR, patient_id, "context", "procedure_steps.json")
        if not os.path.exists(steps_path):
            return JSONResponse({"error": "Procedure steps not yet generated"}, status_code=404)
        with open(steps_path) as f:
            return json.load(f)

    @app.post("/api/patients/{patient_id}/summary")
    async def generate_session_summary(patient_id: str):
        log_path = os.path.join(PATIENTS_DIR, patient_id, "context", "session_log.jsonl")
        if not os.path.exists(log_path):
            return JSONResponse({"error": "No session log found"}, status_code=404)

        entries = []
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        if not entries:
            return JSONResponse({"error": "Session log is empty"}, status_code=404)

        import boto3
        from shared.secrets import secrets

        bedrock = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_BEDROCK_REGION", secrets.get("AWS_BEDROCK_REGION", "us-east-1")),
            aws_access_key_id=os.environ.get("BEDROCK_AWS_ACCESS_KEY_ID", secrets.get("BEDROCK_AWS_ACCESS_KEY_ID", "")),
            aws_secret_access_key=os.environ.get("BEDROCK_AWS_SECRET_ACCESS_KEY", secrets.get("BEDROCK_AWS_SECRET_ACCESS_KEY", "")),
        )
        log_text = "\n".join(f"[{e.get('timestamp', '')}] {e.get('entry', '')}" for e in entries)
        response = await asyncio.to_thread(
            bedrock.converse,
            modelId="us.anthropic.claude-sonnet-4-6",
            messages=[{"role": "user", "content": [{"text": f"Summarize this surgical session log:\n{log_text}"}]}],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
        )
        summary_text = response["output"]["message"]["content"][0]["text"]
        summary_path = os.path.join(PATIENTS_DIR, patient_id, "context", "session_summary.md")
        with open(summary_path, "w") as f:
            f.write(summary_text)
        return {"summary": summary_text, "log_entries": len(entries)}


def _broadcast(patient_id: str, event: dict):
    data = json.dumps(event)
    for q in _prep_subscribers.get(patient_id, []):
        q.put_nowait(data)


async def _run_prep_agent(patient_id: str):
    import base64

    try:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from agents.prep import prep_agent

        _broadcast(patient_id, {"type": "status", "status": "started"})
        info_path = os.path.join(PATIENTS_DIR, patient_id, "info.json")
        with open(info_path) as f:
            info = json.load(f)

        content: list[dict] = [{"type": "text", "text": f"Prepare surgical context for patient_id: {patient_id}."}]
        docs_dir = os.path.join(PATIENTS_DIR, patient_id, "docs")
        for filename in info.get("files", []):
            file_path = os.path.join(docs_dir, filename)
            if not os.path.exists(file_path):
                continue
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            ext = filename.rsplit(".", 1)[-1].lower()
            if ext == "pdf":
                content.append({
                    "type": "file",
                    "mimeType": "application/pdf",
                    "base64": base64.b64encode(file_bytes).decode(),
                    "name": filename.rsplit(".", 1)[0][:64] or "document",
                })

        async for chunk in prep_agent.astream({"messages": [HumanMessage(content=content)]}, stream_mode="updates"):
            for _, node_output in chunk.items():
                if not isinstance(node_output, dict):
                    continue
                for msg in node_output.get("messages", []):
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tc in msg.tool_calls:
                            _broadcast(patient_id, {"type": "tool_call", "tool": tc["name"], "args": tc.get("args", {})})
                    elif isinstance(msg, ToolMessage):
                        _broadcast(patient_id, {"type": "tool_result", "tool": msg.name or "unknown", "result_preview": str(msg.content)[:300]})

        try:
            from shared.indexer import index_patient_context

            await index_patient_context(patient_id)
        except Exception as idx_err:
            print(f"[Indexer] Error for patient {patient_id}: {idx_err}")

        _broadcast(patient_id, {"type": "status", "status": "done"})
    except Exception as e:
        _broadcast(patient_id, {"type": "error", "message": str(e)})
