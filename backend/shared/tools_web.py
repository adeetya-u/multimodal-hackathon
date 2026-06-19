"""Web search and extract tools — Tavily API for fetching medical guidelines."""

import httpx
from langchain_core.tools import tool
from typing import Annotated

import os

from shared.secrets import secrets

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") or secrets.get("TAVILY_API_KEY", "")


@tool
async def web_search(
    query: Annotated[str, "Search query for finding medical guidelines, protocols, or current evidence"],
    search_depth: Annotated[str, "Search depth: 'basic' (fast) or 'advanced' (thorough)"] = "advanced",
    max_results: Annotated[int, "Number of results (1-10)"] = 5,
    include_domains: Annotated[list[str] | None, "Restrict to these domains (e.g. ['pubmed.ncbi.nlm.nih.gov', 'who.int'])"] = None,
) -> str:
    """Search the web for medical guidelines, surgical protocols, and evidence-based resources.

    Use this to find:
    - Surgical procedure guidelines and protocols
    - Current best practices and recommendations
    - Safety checklists and step-by-step procedures
    - Drug interactions and contraindication data
    - Recent clinical guidelines from medical bodies
    """
    if not TAVILY_API_KEY:
        return "Web search is not configured (missing TAVILY_API_KEY)."

    payload: dict = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": search_depth,
        "max_results": min(max(max_results, 1), 10),
        "include_answer": True,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return f"Search error: {e}"

    results = data.get("results", [])
    if not results:
        return "No results found."

    lines = []
    answer = data.get("answer")
    if answer:
        lines.append(f"Summary: {answer}\n")

    for i, res in enumerate(results, 1):
        title = res.get("title", "")
        url = res.get("url", "")
        content = res.get("content", "")[:1500]
        score = res.get("score", 0)
        lines.append(f"[{i}] {title}\n    URL: {url}\n    Relevance: {score:.2f}\n    {content}\n")

    return "\n".join(lines)


@tool
async def web_extract(
    urls: Annotated[list[str], "URLs to extract content from (1-5 URLs)"],
    query: Annotated[str | None, "Optional query to extract only relevant chunks"] = None,
) -> str:
    """Extract full text content from specific web pages. Use after web_search to read the full content of relevant pages.

    Best for reading:
    - Clinical guideline PDFs/pages
    - Surgical protocol documents
    - Drug interaction databases
    - Medical society recommendation pages
    """
    if not TAVILY_API_KEY:
        return "Web extract is not configured (missing TAVILY_API_KEY)."

    urls = urls[:5]
    payload: dict = {
        "api_key": TAVILY_API_KEY,
        "urls": urls,
    }
    if query:
        payload["extract_depth"] = "advanced"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("https://api.tavily.com/extract", json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return f"Extract error: {e}"

    results = data.get("results", [])
    if not results:
        return "No content extracted."

    lines = []
    for res in results:
        url = res.get("url", "")
        content = res.get("raw_content", "")[:5000]
        lines.append(f"=== {url} ===\n{content}\n")

    failed = data.get("failed_results", [])
    if failed:
        lines.append(f"\nFailed URLs: {[f.get('url') for f in failed]}")

    return "\n".join(lines)
