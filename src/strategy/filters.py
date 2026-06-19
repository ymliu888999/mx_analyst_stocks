from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterResult:
    pass_filter: bool
    fail_reasons: list[str]
    warnings: list[str]

    @property
    def explanation(self) -> str:
        parts = []
        if self.fail_reasons:
            parts.append("reject:" + ",".join(self.fail_reasons))
        if self.warnings:
            parts.append("warning:" + ",".join(self.warnings))
        return "; ".join(parts) if parts else "pass"


def _is_true(value: object) -> bool:
    return value in {True, 1, "1", "true", "True", "yes"}


def evaluate_candidate(candidate: dict, config: dict) -> FilterResult:
    fail: list[str] = []
    warnings: list[str] = []

    if _is_true(candidate.get("is_st")):
        fail.append("is_st")
    listing_days = candidate.get("listing_days")
    if listing_days is not None and listing_days < config.get("min_listing_days", 365):
        fail.append("listing_days_below_min")
    avg_amount = candidate.get("avg_amount_20d")
    if avg_amount is not None and avg_amount < config.get("min_avg_amount_20d", 0):
        fail.append("avg_amount_20d_below_min")
    if candidate.get("has_severe_risk"):
        fail.append("severe_risk_event")

    broker_count = candidate.get("effective_broker_count") or 0
    star_count = candidate.get("effective_star_analyst_count") or 0
    min_broker = config.get("min_broker_count", 1)
    min_star = config.get("min_star_analyst_count", 1)
    if broker_count < min_broker:
        fail.append("effective_broker_count_below_2")
    if star_count < min_star:
        fail.append("effective_star_analyst_count_below_2")

    upside = candidate.get("target_upside")
    if upside is None:
        fail.append("target_upside_missing")
    else:
        if upside < config.get("min_target_upside", 0.25):
            fail.append("target_upside_below_min")
        if upside > config.get("max_target_upside", 1.0):
            fail.append("target_upside_above_max")

    post_return = candidate.get("post_report_return")
    if post_return is not None:
        if post_return > config.get("max_post_report_return", 0.12):
            fail.append("post_report_return_above_max")
        if post_return < config.get("min_post_report_return", -0.08):
            warnings.append("post_report_return_below_min")

    return_20d = candidate.get("return_20d")
    if return_20d is not None and return_20d > config.get("max_return_20d", 0.35):
        fail.append("return_20d_above_max")
    return_60d = candidate.get("return_60d")
    if return_60d is not None and return_60d > config.get("max_return_60d", 0.80):
        fail.append("return_60d_above_max")

    latest_close = candidate.get("latest_close")
    ma60 = candidate.get("ma60")
    if latest_close is not None and ma60 is not None and latest_close < ma60:
        warnings.append("price_below_ma60")
    if candidate.get("has_medium_risk"):
        warnings.append("medium_risk_event")
    if candidate.get("uncertain_match"):
        warnings.append("uncertain_star_analyst_match")

    return FilterResult(pass_filter=not fail, fail_reasons=fail, warnings=warnings)
