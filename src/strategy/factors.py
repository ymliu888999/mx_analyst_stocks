from __future__ import annotations


def safe_ratio(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round(current / previous - 1, 6)


def compute_target_upside(latest_close: float | None, target_price: float | None) -> float | None:
    return safe_ratio(target_price, latest_close)


def compute_target_revision(current_target: float | None, previous_target: float | None) -> float | None:
    return safe_ratio(current_target, previous_target)


def compute_earnings_revision(current_value: float | None, previous_value: float | None) -> float | None:
    return safe_ratio(current_value, previous_value)


def compute_post_report_return(
    latest_close: float | None, close_before_first_report: float | None
) -> float | None:
    return safe_ratio(latest_close, close_before_first_report)


def compute_trend_score(
    latest_close: float | None, ma20: float | None = None, ma60: float | None = None
) -> float | None:
    if latest_close is None:
        return None
    score = 0.0
    checks = 0
    if ma20 is not None:
        checks += 1
        score += 1.0 if latest_close >= ma20 else 0.0
    if ma60 is not None:
        checks += 1
        score += 1.0 if latest_close >= ma60 else 0.0
    if checks == 0:
        return None
    return round(score / checks, 6)
