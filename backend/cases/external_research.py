"""External web research — one tool call when local knowledge search is empty."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .llm import converse, extract_message_text
from .prompts import build_external_answer_prompt
from .workers import AnswerResult, REFUSAL_A_TEMPLATE, clamp_spoken_text

EXTERNAL_SEARCH_TOOL = {
    "toolSpec": {
        "name": "external_web_search",
        "description": (
            "Search public clinical references when the local patient chart and SOP index "
            "return no hits. Call at most once per question."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Focused medical search query (drug, dose, guideline, technique).",
                    }
                },
                "required": ["query"],
            }
        },
    }
}


def external_search_enabled() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY", "").strip())


async def external_web_search(query: str) -> tuple[str, str, str]:
    """Return formatted results, primary source label, and excerpt for display."""
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return "", "", ""

    payload = {
        "api_key": api_key,
        "query": query.strip(),
        "max_results": 4,
        "search_depth": "basic",
        "include_answer": True,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return "", "", ""

    lines: list[str] = []
    answer = str(data.get("answer", "")).strip()
    if answer:
        lines.append(f"Summary: {answer}")

    top_source = ""
    top_excerpt = ""
    for index, hit in enumerate(data.get("results", [])[:4]):
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title", "")).strip()
        url = str(hit.get("url", "")).strip()
        content = str(hit.get("content", "")).strip()
        if index == 0:
            top_source = url or title
            top_excerpt = content[:600]
        if title or content:
            lines.append(f"- {title or url}: {content[:400]}")

    return "\n".join(lines), top_source, top_excerpt


def _tool_uses(message: dict) -> list[dict[str, Any]]:
    uses: list[dict[str, Any]] = []
    for block in message.get("content", []):
        tool_use = block.get("toolUse")
        if isinstance(tool_use, dict):
            uses.append(tool_use)
    return uses


async def run_external_answer(
    query: str,
    *,
    live_context: str = "",
    procedure: str = "",
) -> AnswerResult:
    if not external_search_enabled():
        return AnswerResult(grounded_ids=[], spoken_text="", refusal=True)

    prompt = build_external_answer_prompt(
        query=query,
        live_context=live_context,
        procedure=procedure,
    )
    tool_config = {"tools": [EXTERNAL_SEARCH_TOOL]}
    first = await asyncio.to_thread(
        converse,
        [{"role": "user", "content": [{"text": prompt}]}],
        max_tokens=280,
        temperature=0.1,
        tool_config=tool_config,
    )
    if not first:
        return AnswerResult(grounded_ids=[], spoken_text=REFUSAL_A_TEMPLATE, refusal=True)

    assistant_message = first["output"]["message"]
    tool_calls = _tool_uses(assistant_message)
    if not tool_calls:
        spoken = clamp_spoken_text(extract_message_text(assistant_message))
        if spoken:
            return AnswerResult(
                grounded_ids=["external"],
                spoken_text=spoken,
                external=True,
                external_source="external reference",
                external_excerpt=spoken,
            )
        return AnswerResult(grounded_ids=[], spoken_text=REFUSAL_A_TEMPLATE, refusal=True)

    tool_use = tool_calls[0]
    search_query = str(tool_use.get("input", {}).get("query", query)).strip() or query
    results, source, excerpt = await external_web_search(search_query)
    if not results:
        return AnswerResult(grounded_ids=[], spoken_text="", refusal=True)

    messages = [
        {"role": "user", "content": [{"text": prompt}]},
        {"role": "assistant", "content": assistant_message["content"]},
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"text": results}],
                        "status": "success",
                    }
                }
            ],
        },
    ]
    final = await asyncio.to_thread(
        converse,
        messages,
        max_tokens=120,
        temperature=0.1,
    )
    if not final:
        return AnswerResult(grounded_ids=[], spoken_text=REFUSAL_A_TEMPLATE, refusal=True)

    spoken = clamp_spoken_text(extract_message_text(final["output"]["message"]))
    if not spoken:
        return AnswerResult(grounded_ids=[], spoken_text=REFUSAL_A_TEMPLATE, refusal=True)

    return AnswerResult(
        grounded_ids=["external"],
        spoken_text=spoken,
        external=True,
        external_source=source or "external reference",
        external_excerpt=excerpt or spoken,
    )
