from __future__ import annotations


def clamp(value: float | None, low: float = 0.0, high: float = 1.0) -> float:
    if value is None:
        return 0.5
    return max(low, min(high, value))


def _revision_score(value: float | None) -> float:
    if value is None:
        return 0.5
    return clamp((value + 0.10) / 0.30)


def _price_reaction_score(value: float | None) -> float:
    if value is None:
        return 0.5
    if value < -0.08:
        return 0.2
    if value > 0.12:
        return 0.0
    return clamp(1 - abs(value) / 0.12)


def score_candidate(candidate: dict, config: dict) -> dict:
    weights = config.get("weights", {})
    upside_score = clamp(candidate.get("target_upside"))
    broker_count = candidate.get("effective_broker_count") or 0
    star_count = candidate.get("effective_star_analyst_count") or 0
    consensus_score = clamp(min(broker_count, star_count) / 2)
    target_revision_score = _revision_score(candidate.get("target_price_revision"))
    earnings_revision_score = _revision_score(candidate.get("earnings_revision"))
    price_reaction_score = _price_reaction_score(candidate.get("post_report_return"))
    trend_score = clamp(candidate.get("trend_score"))
    risk_penalty = clamp(candidate.get("risk_penalty"), 0, 1)

    total = (
        upside_score * weights.get("target_upside", 0.25)
        + consensus_score * weights.get("star_consensus", 0.20)
        + target_revision_score * weights.get("target_revision", 0.20)
        + earnings_revision_score * weights.get("earnings_revision", 0.15)
        + price_reaction_score * weights.get("price_reaction", 0.10)
        + trend_score * weights.get("trend", 0.10)
    )
    total = clamp(total - risk_penalty)
    return {
        **candidate,
        "upside_score": round(upside_score, 6),
        "consensus_score": round(consensus_score, 6),
        "target_revision_score": round(target_revision_score, 6),
        "earnings_revision_score": round(earnings_revision_score, 6),
        "price_reaction_score": round(price_reaction_score, 6),
        "trend_score": round(trend_score, 6),
        "risk_penalty": round(risk_penalty, 6),
        "total_score": round(total, 6),
    }
