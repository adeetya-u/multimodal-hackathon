"""PubMed search tool — searches PubMed and returns ranked results with evidence tiers."""

import json
from typing import Annotated

import httpx
from langchain_core.tools import StructuredTool

from shared.pubmed.client import search, fetch_summaries
from shared.pubmed.evidence import classify_evidence_tier, rank_results

PUBMED_SEARCH_DESCRIPTION = """Search PubMed for peer-reviewed medical literature.

Returns up to 20 results ranked by evidence tier (Systematic Reviews > Meta-Analyses > RCTs > ...).
Retracted papers are automatically excluded.

Use this tool to find:
- Recent clinical evidence, trials, or studies
- Current treatment guidelines and protocols
- Drug efficacy or safety data
- Surgical technique studies and outcomes
- Any medical topic requiring citable, peer-reviewed sources

QUERY CONSTRUCTION RULES:
- Keep queries SHORT: 2-3 MeSH/keyword terms joined by AND.
- BAD: "total knee arthroplasty guidelines 2024 penicillin allergy antibiotic prophylaxis"
- GOOD: "knee arthroplasty"[MeSH Terms] AND "antibiotic prophylaxis"[MeSH Terms]
- Do NOT put year numbers in the query. Use date_range_years parameter instead.
- Use pub_types parameter for filtering by publication type.
- If 0 results, SIMPLIFY the query (fewer terms).

Result format: [Evidence Tier . Year] Title [PMID: XXXXX]"""


async def _pubmed_search(
    query: Annotated[str, "PubMed search query. Keep SHORT: 2-3 core terms joined by AND. Example: '\"knee arthroplasty\"[MeSH Terms] AND \"VTE prophylaxis\"[MeSH Terms]'"],
    pub_types: Annotated[list[str] | None, "Filter by publication type: 'Meta-Analysis', 'Systematic Review', 'Randomized Controlled Trial', 'Clinical Trial', 'Review', 'Practice Guideline', 'Case Reports'. Null for all."] = None,
    max_results: Annotated[int, "Maximum results (1-20). Default 10."] = 10,
    date_range_years: Annotated[int | None, "Limit to papers from last N years. Null for all time."] = None,
) -> str:
    max_results = min(max_results, 20)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            result = await search(client, query, pub_types, max_results, date_range_years)
            pmids = result.get("idlist", [])
            total = int(result.get("count", 0))
            query_translation = result.get("querytranslation", query)

            if not pmids:
                return json.dumps({
                    "query_used": query_translation,
                    "total_results": total,
                    "results": [],
                    "message": "No results found. Try broadening the query or removing pub_type filters.",
                })

            summaries = await fetch_summaries(client, pmids)

            results = []
            for pmid in pmids:
                s = summaries.get(pmid, {})
                if not isinstance(s, dict) or "title" not in s:
                    continue
                authors_raw = s.get("authors", [])
                authors = [a["name"] for a in authors_raw if isinstance(a, dict)] if authors_raw else []
                pub_types_raw = s.get("pubtype", [])
                tier, label = classify_evidence_tier(pub_types_raw)
                results.append({
                    "pmid": pmid,
                    "title": s.get("title", ""),
                    "authors": authors[:3],
                    "journal": s.get("source", ""),
                    "pub_date": s.get("pubdate", ""),
                    "evidence_tier": tier,
                    "evidence_label": label,
                })

            ranked = rank_results(results)

            return json.dumps({
                "query_used": query_translation,
                "total_results": total,
                "results": ranked,
            }, indent=2)
    except Exception as e:
        return f"PubMed search error: {e}"


pubmed_search = StructuredTool.from_function(
    name="pubmed_search",
    description=PUBMED_SEARCH_DESCRIPTION,
    coroutine=_pubmed_search,
)
