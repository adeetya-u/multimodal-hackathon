"""Evidence tier classification for PubMed results."""

TIER_MAP = {
    "Systematic Review": (1, "Systematic Review"),
    "Meta-Analysis": (2, "Meta-Analysis"),
    "Randomized Controlled Trial": (3, "RCT"),
    "Clinical Trial": (4, "Clinical Trial"),
    "Observational Study": (5, "Observational"),
    "Cohort Study": (5, "Cohort"),
    "Practice Guideline": (6, "Practice Guideline"),
    "Guideline": (6, "Guideline"),
    "Review": (7, "Review"),
    "Case Reports": (8, "Case Report"),
    "Editorial": (9, "Editorial"),
    "Letter": (9, "Letter"),
    "Comment": (9, "Comment"),
}


def classify_evidence_tier(pub_types: list[str]) -> tuple[int, str]:
    best_tier = 9
    best_label = "Other"
    for pt in pub_types:
        if pt in TIER_MAP:
            tier, label = TIER_MAP[pt]
            if tier < best_tier:
                best_tier = tier
                best_label = label
    return best_tier, best_label


def rank_results(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: (r.get("evidence_tier", 9), -(int(r.get("pub_date", "0")[:4]) if r.get("pub_date") else 0)))
