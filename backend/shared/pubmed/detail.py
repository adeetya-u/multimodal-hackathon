"""PubMed detail tool — fetch abstract, generate citation, or find related articles."""

import json
from typing import Annotated, Literal

import httpx
from langchain_core.tools import StructuredTool

from shared.pubmed.client import fetch_abstract, fetch_summaries, find_related
from shared.pubmed.evidence import classify_evidence_tier, rank_results

PUBMED_DETAIL_DESCRIPTION = """Get details about a specific PubMed article by PMID.

Actions available:
1. action="abstract" (default): Fetch structured abstract, MeSH terms, DOI, evidence tier.
2. action="related": Find similar articles via citation similarity.

Use after pubmed_search to read abstracts of relevant papers."""


async def _pubmed_detail(
    pmid: Annotated[str, "PubMed ID (PMID). Numeric string, e.g. '36041474'."],
    action: Annotated[Literal["abstract", "related"], "Action: 'abstract' (fetch details) or 'related' (find similar papers)."] = "abstract",
    max_results: Annotated[int, "Max related papers (1-10, for action='related'). Default 5."] = 5,
) -> str:
    try:
        if action == "abstract":
            return await _fetch_abstract(pmid)
        elif action == "related":
            return await _find_related(pmid, max_results)
        return f"Unknown action: {action}"
    except Exception as e:
        return f"PubMed detail error: {e}"


async def _fetch_abstract(pmid: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        article = await fetch_abstract(client, pmid)

    if "error" in article:
        return json.dumps({"error": article["error"], "pmid": pmid})

    tier, label = classify_evidence_tier(article.get("pub_types", []))

    return json.dumps({
        "pmid": article["pmid"],
        "title": article["title"],
        "authors": article["authors"][:5],
        "journal": article["journal"],
        "year": article["year"],
        "doi": article.get("doi"),
        "pmc_id": article.get("pmc_id"),
        "abstract": article["abstract"],
        "mesh_terms": article["mesh_terms"][:10],
        "evidence_tier": tier,
        "evidence_label": label,
    }, indent=2)


async def _find_related(pmid: str, max_results: int) -> str:
    max_results = min(max_results, 10)
    async with httpx.AsyncClient(timeout=30.0) as client:
        related_pmids = await find_related(client, pmid)
        if not related_pmids:
            return json.dumps({"pmid": pmid, "results": [], "message": "No related articles found."})

        pmids_to_fetch = related_pmids[:max_results]
        summaries = await fetch_summaries(client, pmids_to_fetch)

    results = []
    for rpmid in pmids_to_fetch:
        s = summaries.get(rpmid, {})
        if not isinstance(s, dict) or "title" not in s:
            continue
        authors_raw = s.get("authors", [])
        authors = [a["name"] for a in authors_raw if isinstance(a, dict)] if authors_raw else []
        pub_types_raw = s.get("pubtype", [])
        tier, label = classify_evidence_tier(pub_types_raw)
        results.append({
            "pmid": rpmid,
            "title": s.get("title", ""),
            "authors": authors[:3],
            "journal": s.get("source", ""),
            "pub_date": s.get("pubdate", ""),
            "evidence_tier": tier,
            "evidence_label": label,
        })

    ranked = rank_results(results)
    return json.dumps({"seed_pmid": pmid, "results": ranked}, indent=2)


pubmed_detail = StructuredTool.from_function(
    name="pubmed_detail",
    description=PUBMED_DETAIL_DESCRIPTION,
    coroutine=_pubmed_detail,
)
