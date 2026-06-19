"""Provider health checks for API diagnostics."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

import httpx

from .bootstrap import bootstrap_to_gzip, build_bootstrap_payload
from .llm import converse_text, llm_provider
from .search import KnowledgeSearch
from .store import CaseStore, case_data_root
from .types import Snippet

CheckStatus = Literal["pass", "fail", "skip", "warn"]


@dataclass
class ProviderCheck:
    name: str
    status: CheckStatus
    detail: str
    latency_ms: int | None = None
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def check_case_store() -> ProviderCheck:
    t0 = time.monotonic()
    try:
        root = case_data_root()
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        cases = len(CaseStore().list_cases())
        return ProviderCheck(
            "case_store",
            "pass",
            f"writable at {root}, {cases} case(s)",
            _ms(t0),
        )
    except Exception as exc:
        return ProviderCheck("case_store", "fail", str(exc), _ms(t0))


async def check_unsiloed() -> ProviderCheck:
    api_key = os.environ.get("UNSILOED_API_KEY", "").strip()
    if not api_key:
        return ProviderCheck(
            "unsiloed",
            "warn",
            "UNSILOED_API_KEY not set — PDF parse uses text fallback",
            required=False,
        )
    url = os.environ.get("UNSILOED_PARSE_URL", "https://prod.visionapi.unsiloed.ai/parse")
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url.replace("/parse", ""), headers={"api-key": api_key})
        return ProviderCheck("unsiloed", "pass", f"host reachable (HTTP {res.status_code})", _ms(t0), required=False)
    except Exception as exc:
        return ProviderCheck("unsiloed", "fail", str(exc), _ms(t0), required=False)


async def check_moss_cloud() -> ProviderCheck:
    pid = os.environ.get("MOSS_PROJECT_ID", "").strip()
    pkey = os.environ.get("MOSS_PROJECT_KEY", "").strip()
    if not (pid and pkey):
        return ProviderCheck(
            "moss_cloud",
            "skip",
            "MOSS_PROJECT_ID/KEY not set — using local keyword index",
            required=False,
        )
    t0 = time.monotonic()
    try:
        from moss import DocumentInfo, MossClient

        client = MossClient(pid, pkey)
        docs = [
            DocumentInfo(
                id="health-1",
                text="Total knee arthroplasty surgical timeout.",
                metadata={"type": "sop", "source": "health"},
            )
        ]
        index_name = f"health-{int(time.time())}"
        result = await client.create_index(index_name, docs, os.environ.get("MOSS_MODEL_ID", "moss-minilm"))
        loaded = await client.load_index(getattr(result, "index_name", index_name))
        hits = await client.query(loaded, "surgical timeout", k=1)
        await client.delete_index(getattr(result, "index_name", index_name))
        return ProviderCheck(
            "moss_cloud",
            "pass" if hits else "warn",
            f"create/load/query ok, hits={len(hits)}",
            _ms(t0),
            required=False,
        )
    except ImportError:
        return ProviderCheck("moss_cloud", "skip", "moss package not installed", required=False)
    except Exception as exc:
        return ProviderCheck("moss_cloud", "fail", str(exc), _ms(t0), required=False)


async def check_moss_local() -> ProviderCheck:
    t0 = time.monotonic()
    try:
        samples = [
            Snippet(source="sop/timeout", text="Surgical timeout and site verification.", chunk_id="timeout"),
            Snippet(source="patient/chart", text="Type 2 diabetes, hypertension.", chunk_id="chart"),
        ]
        store = KnowledgeSearch(samples)
        hits = await store.search("surgical timeout", k=2)
        return ProviderCheck(
            "moss_local",
            "pass" if hits else "fail",
            f"keyword index, hits={len(hits)}",
            _ms(t0),
            required=False,
        )
    except Exception as exc:
        return ProviderCheck("moss_local", "fail", str(exc), _ms(t0), required=False)


async def check_minimax(*, required: bool | None = None) -> ProviderCheck:
    active = llm_provider() == "minimax"
    if required is None:
        required = active
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not api_key:
        if active:
            return ProviderCheck("minimax", "fail", "MINIMAX_API_KEY not set", _ms(time.monotonic()))
        return ProviderCheck(
            "minimax",
            "skip",
            "MINIMAX_API_KEY not set — compaction uses truncation",
            required=False,
        )
    base = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1").rstrip("/")
    model = os.environ.get("MINIMAX_LLM_MODEL", "MiniMax-M2.1")
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say ok"}],
                    "max_tokens": 8,
                },
            )
        if res.status_code != 200:
            return ProviderCheck("minimax", "fail", f"HTTP {res.status_code}: {res.text[:80]}", _ms(t0), required=required)
        reply = res.json()["choices"][0]["message"]["content"]
        return ProviderCheck("minimax", "pass", f"model={model}, reply={reply[:30]!r}", _ms(t0), required=required)
    except Exception as exc:
        return ProviderCheck("minimax", "fail", str(exc), _ms(t0), required=required)


async def check_case_artifacts(case_id: str) -> ProviderCheck:
    t0 = time.monotonic()
    try:
        store = CaseStore()
        meta = store.get_metadata(case_id)
        case_dir = store.case_dir(case_id)
        artifacts = {
            "checklist.json": (case_dir / "checklist.json").exists(),
            "patient_context.json": (case_dir / "patient_context.json").exists(),
            "moss_snippets.json": (case_dir / "moss_snippets.json").exists(),
            "context_window.json": (case_dir / "context_window.json").exists(),
        }
        missing = [k for k, v in artifacts.items() if not v]
        snippet_count = 0
        if artifacts["moss_snippets.json"]:
            import json

            snippet_count = len(json.loads((case_dir / "moss_snippets.json").read_text()))
        status: CheckStatus = "pass" if not missing else ("warn" if meta.stage.value != "ready" else "fail")
        detail = f"stage={meta.stage.value}, snippets={snippet_count}"
        if missing:
            detail += f", missing={missing}"
        return ProviderCheck("case_artifacts", status, detail, _ms(t0))
    except FileNotFoundError:
        return ProviderCheck("case_artifacts", "fail", f"case not found: {case_id}", _ms(t0))
    except Exception as exc:
        return ProviderCheck("case_artifacts", "fail", str(exc), _ms(t0))


async def check_case_bootstrap(case_id: str) -> ProviderCheck:
    t0 = time.monotonic()
    try:
        payload = build_bootstrap_payload(case_id)
        gz = bootstrap_to_gzip(payload)
        snippets = len(payload.get("snippets", []))
        return ProviderCheck(
            "case_bootstrap",
            "pass",
            f"{snippets} snippets, gzip={len(gz)} bytes",
            _ms(t0),
        )
    except Exception as exc:
        return ProviderCheck("case_bootstrap", "fail", str(exc), _ms(t0))


async def check_nebius() -> ProviderCheck:
    t0 = time.monotonic()
    if llm_provider() != "nebius":
        return ProviderCheck(
            "nebius",
            "skip",
            f"LLM_PROVIDER is {llm_provider()}",
            _ms(t0),
            required=False,
        )
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key:
        return ProviderCheck("nebius", "fail", "NEBIUS_API_KEY not set", _ms(t0))
    model = os.environ.get("NEBIUS_MODEL_DEFAULT", "meta-llama/Llama-3.3-70B-Instruct")
    raw = await asyncio.to_thread(converse_text, "ping", model=model, max_tokens=5, temperature=0)
    if raw is None:
        return ProviderCheck("nebius", "fail", "Nebius converse failed", _ms(t0))
    return ProviderCheck("nebius", "pass", f"model={model}", _ms(t0))


async def check_vapi() -> ProviderCheck:
    t0 = time.monotonic()
    from .voice import intro_assistant_id, or_assistant_id, public_key

    if not public_key() or not or_assistant_id():
        return ProviderCheck("vapi", "fail", "VAPI_PUBLIC_KEY or VAPI_OR_ASSISTANT_ID missing", _ms(t0))
    intro = intro_assistant_id()
    detail = f"or={or_assistant_id()[:12]}…"
    if intro:
        detail += f", intro={intro[:12]}…"
    return ProviderCheck("vapi", "pass", detail, _ms(t0))


async def check_insforge() -> ProviderCheck:
    t0 = time.monotonic()
    if os.environ.get("STORAGE_BACKEND", "filesystem").strip().lower() != "insforge":
        return ProviderCheck("insforge", "skip", "STORAGE_BACKEND is filesystem", _ms(t0), required=False)
    url = os.environ.get("INSFORGE_URL", "").strip()
    key = os.environ.get("INSFORGE_SERVICE_KEY", "").strip() or os.environ.get("INSFORGE_ANON_KEY", "").strip()
    if not url or not key:
        return ProviderCheck("insforge", "fail", "INSFORGE_URL or INSFORGE_SERVICE_KEY missing", _ms(t0))
    return ProviderCheck("insforge", "pass", f"url={url}", _ms(t0))


async def run_provider_checks(*, case_id: str | None = None, deep: bool = True) -> dict[str, Any]:
    """Run checks in parallel. `deep=False` skips slow external calls."""
    tasks = [
        check_case_store(),
        check_nebius(),
        check_minimax(),
        check_vapi(),
        check_insforge(),
        check_moss_local(),
    ]
    if deep:
        tasks.extend([check_unsiloed(), check_moss_cloud()])
    if case_id:
        tasks.extend([check_case_artifacts(case_id), check_case_bootstrap(case_id)])

    results = await asyncio.gather(*tasks, return_exceptions=True)
    checks: list[ProviderCheck] = []
    for item in results:
        if isinstance(item, Exception):
            checks.append(ProviderCheck("unknown", "fail", str(item)))
        else:
            checks.append(item)

    required_failed = [c.name for c in checks if c.required and c.status == "fail"]
    llm_name = "minimax" if llm_provider() == "minimax" else "nebius"
    voice_ready = not any(c.name in {llm_name, "vapi"} and c.status == "fail" for c in checks)

    return {
        "ok": len(required_failed) == 0,
        "voice_ready": voice_ready,
        "required_failed": required_failed,
        "checks": [c.to_dict() for c in checks],
        "checked_at": time.time(),
    }
