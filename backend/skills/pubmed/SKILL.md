# PubMed Research Skill

Search and analyze peer-reviewed medical literature from PubMed/MEDLINE.

## Tools
- `pubmed_search` — Search PubMed with evidence tier ranking
- `pubmed_detail` — Fetch abstracts or find related articles
- `web_search` — Supplement with guideline searches
- `web_extract` — Read full guideline pages

## Evidence Tier Hierarchy

| Tier | Type | Weight |
|------|------|--------|
| 1 | Systematic Review / Cochrane | Highest |
| 2 | Meta-Analysis | |
| 3 | Randomized Controlled Trial | |
| 4 | Clinical Trial | |
| 5 | Observational / Cohort Study | |
| 6 | Practice Guideline | |
| 7 | Review | |
| 8 | Case Report | |
| 9 | Editorial / Letter / Other | Lowest |

## Workflow for Surgery Prep

1. **Search for procedure evidence**:
   - `pubmed_search` with procedure MeSH terms + "outcomes" or "technique"
   - Filter by pub_types: "Systematic Review", "Practice Guideline", "Meta-Analysis"
   - Use date_range_years=5 for current evidence

2. **Search for patient-specific evidence**:
   - Comorbidity + procedure interactions (e.g. "diabetes" AND "knee arthroplasty")
   - Drug management peri-operatively (e.g. "metformin" AND "perioperative")
   - Allergy alternatives (e.g. "penicillin allergy" AND "surgical prophylaxis")

3. **Triage by evidence tier**: Prioritize Tier 1-3 papers

4. **Deep dive**: Use `pubmed_detail` action="abstract" for top papers

5. **Supplement with guidelines**: Use `web_search` for:
   - Society guidelines (NICE, AAOS, ASA, ERAS)
   - Include domains: nice.org.uk, aaos.org, asahq.org

## Query Construction Rules

- Keep queries SHORT: 2-3 MeSH terms joined by AND
- PubMed auto-expands terms into synonyms — more AND = fewer results
- Do NOT include years in the query string — use `date_range_years` param
- Do NOT include organization names unless searching a specific paper
- If 0 results: SIMPLIFY (fewer terms), don't add more

### Good queries:
```
"arthroplasty, replacement, knee"[MeSH] AND "anticoagulants"[MeSH]
"knee prosthesis"[MeSH] AND "surgical wound infection"[MeSH]
"anesthesia, spinal"[MeSH] AND "obesity"[MeSH]
```

### Bad queries:
```
total knee arthroplasty TKA guidelines 2024 AAOS antibiotic prophylaxis penicillin allergy
```
