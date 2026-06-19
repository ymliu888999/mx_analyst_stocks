from __future__ import annotations

from collections import defaultdict


def select_portfolio(
    candidates: list[dict], size: int = 8, max_per_industry: int = 2
) -> list[dict]:
    selected: list[dict] = []
    industry_count: dict[str, int] = defaultdict(int)
    ranked = sorted(
        [row for row in candidates if row.get("pass_filter") in {1, True}],
        key=lambda row: row.get("total_score") or 0,
        reverse=True,
    )
    for row in ranked:
        industry = row.get("industry") or "UNKNOWN"
        if industry_count[industry] >= max_per_industry:
            continue
        selected.append({**row})
        industry_count[industry] += 1
        if len(selected) >= size:
            break
    if selected:
        weight = 1 / len(selected)
        for idx, row in enumerate(selected, 1):
            row["rank"] = idx
            row["weight"] = weight
    return selected
