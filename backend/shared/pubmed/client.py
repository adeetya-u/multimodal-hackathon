"""PubMed E-utilities client — direct NCBI API calls."""

import httpx

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def search(
    client: httpx.AsyncClient,
    query: str,
    pub_types: list[str] | None = None,
    max_results: int = 10,
    date_range_years: int | None = None,
) -> dict:
    params: dict = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    if pub_types:
        type_filter = " OR ".join(f'"{pt}"[pt]' for pt in pub_types)
        params["term"] = f"({query}) AND ({type_filter})"
    if date_range_years:
        params["datetype"] = "pdat"
        params["reldate"] = date_range_years * 365

    # Exclude retracted
    params["term"] = f"({params['term']}) NOT retracted publication[pt]"

    r = await client.get(f"{BASE_URL}/esearch.fcgi", params=params)
    r.raise_for_status()
    data = r.json()
    result = data.get("esearchresult", {})
    return result


async def fetch_summaries(client: httpx.AsyncClient, pmids: list[str]) -> dict:
    if not pmids:
        return {}
    r = await client.get(
        f"{BASE_URL}/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
    )
    r.raise_for_status()
    data = r.json()
    return data.get("result", {})


async def fetch_abstract(client: httpx.AsyncClient, pmid: str) -> dict:
    r = await client.get(
        f"{BASE_URL}/efetch.fcgi",
        params={"db": "pubmed", "id": pmid, "rettype": "xml", "retmode": "xml"},
    )
    r.raise_for_status()

    import xml.etree.ElementTree as ET
    root = ET.fromstring(r.text)
    article = root.find(".//PubmedArticle")
    if article is None:
        return {"error": f"No article found for PMID {pmid}"}

    medline = article.find(".//MedlineCitation")
    art = medline.find(".//Article") if medline else None
    if art is None:
        return {"error": "Article element not found"}

    title_el = art.find("ArticleTitle")
    title = title_el.text if title_el is not None else ""

    # Authors
    authors = []
    for author in art.findall(".//Author"):
        last = author.findtext("LastName", "")
        first = author.findtext("ForeName", "")
        if last:
            authors.append(f"{last} {first}".strip())

    # Journal
    journal_el = art.find(".//Journal/Title")
    journal = journal_el.text if journal_el is not None else ""

    # Year
    year_el = art.find(".//PubDate/Year")
    year = year_el.text if year_el is not None else ""

    # Abstract
    abstract_parts = {}
    for abs_text in art.findall(".//Abstract/AbstractText"):
        label = abs_text.get("Label", "MAIN")
        text = "".join(abs_text.itertext())
        abstract_parts[label] = text

    # DOI
    doi = None
    for id_el in article.findall(".//ArticleId"):
        if id_el.get("IdType") == "doi":
            doi = id_el.text

    # PMC ID
    pmc_id = None
    for id_el in article.findall(".//ArticleId"):
        if id_el.get("IdType") == "pmc":
            pmc_id = id_el.text

    # Pub types
    pub_types = [pt.text for pt in art.findall(".//PublicationType") if pt.text]

    # MeSH
    mesh_terms = [m.findtext("DescriptorName", "") for m in medline.findall(".//MeshHeading")] if medline else []

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "doi": doi,
        "pmc_id": pmc_id,
        "abstract": abstract_parts,
        "pub_types": pub_types,
        "mesh_terms": [m for m in mesh_terms if m],
    }


async def find_related(client: httpx.AsyncClient, pmid: str) -> list[str]:
    r = await client.get(
        f"{BASE_URL}/elink.fcgi",
        params={"dbfrom": "pubmed", "db": "pubmed", "id": pmid, "cmd": "neighbor_score", "retmode": "json"},
    )
    r.raise_for_status()
    data = r.json()
    linksets = data.get("linksets", [])
    if not linksets:
        return []
    links = linksets[0].get("linksetdbs", [])
    for ls in links:
        if ls.get("linkname") == "pubmed_pubmed":
            return [link["id"] for link in ls.get("links", [])][:20]
    return []
