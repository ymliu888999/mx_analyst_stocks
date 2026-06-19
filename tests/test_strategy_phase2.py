from src.strategy.factors import (
    compute_earnings_revision,
    compute_post_report_return,
    compute_target_revision,
    compute_target_upside,
    compute_trend_score,
)
from src.strategy.filters import evaluate_candidate
from src.strategy.portfolio import select_portfolio
from src.strategy.scorer import score_candidate


CONFIG = {
    "min_target_upside": 0.25,
    "max_target_upside": 1.0,
    "max_post_report_return": 0.12,
    "min_post_report_return": -0.08,
    "max_return_20d": 0.35,
    "max_return_60d": 0.80,
    "min_avg_amount_20d": 150000000,
    "weights": {
        "target_upside": 0.25,
        "star_consensus": 0.20,
        "target_revision": 0.20,
        "earnings_revision": 0.15,
        "price_reaction": 0.10,
        "trend": 0.10,
    },
}


def test_factor_calculations_use_neutral_defaults_when_history_missing():
    assert compute_target_upside(10, 12.5) == 0.25
    assert compute_target_revision(12, 10) == 0.2
    assert compute_target_revision(12, None) is None
    assert compute_earnings_revision(1.2, 1.0) == 0.2
    assert compute_earnings_revision(1.2, None) is None
    assert compute_post_report_return(11, 10) == 0.1
    assert compute_trend_score(latest_close=11, ma20=10, ma60=9) == 1.0


def test_evaluate_candidate_returns_pass_and_explainable_warnings():
    candidate = {
        "stock_code": "000001",
        "stock_name": "Sample Bank",
        "is_st": 0,
        "listing_days": 900,
        "avg_amount_20d": 200_000_000,
        "effective_broker_count": 2,
        "effective_star_analyst_count": 2,
        "target_upside": 0.35,
        "post_report_return": -0.09,
        "return_20d": 0.10,
        "return_60d": 0.20,
        "latest_close": 10,
        "ma60": 10.5,
        "has_severe_risk": False,
        "has_medium_risk": False,
        "uncertain_match": True,
    }

    result = evaluate_candidate(candidate, CONFIG)

    assert result.pass_filter is True
    assert "post_report_return_below_min" in result.warnings
    assert "price_below_ma60" in result.warnings
    assert "uncertain_star_analyst_match" in result.warnings


def test_evaluate_candidate_rejects_hard_failures_with_reasons():
    candidate = {
        "stock_code": "000002",
        "is_st": 1,
        "listing_days": 100,
        "avg_amount_20d": 50_000_000,
        "effective_broker_count": 1,
        "effective_star_analyst_count": 1,
        "target_upside": 0.1,
        "post_report_return": 0.20,
        "return_20d": 0.50,
        "return_60d": 0.90,
        "has_severe_risk": True,
    }

    result = evaluate_candidate(candidate, CONFIG)

    assert result.pass_filter is False
    assert "is_st" in result.fail_reasons
    assert "target_upside_below_min" in result.fail_reasons
    assert "post_report_return_above_max" in result.fail_reasons


def test_score_candidate_combines_weighted_scores_and_penalty():
    candidate = {
        "target_upside": 0.50,
        "effective_broker_count": 2,
        "effective_star_analyst_count": 2,
        "target_price_revision": 0.10,
        "earnings_revision": None,
        "post_report_return": 0.02,
        "trend_score": 1.0,
        "risk_penalty": 0.10,
    }

    scored = score_candidate(candidate, CONFIG)

    assert scored["upside_score"] == 0.5
    assert scored["consensus_score"] == 1.0
    assert scored["earnings_revision_score"] == 0.5
    assert 0 < scored["total_score"] < 1


def test_select_portfolio_caps_industry_and_weights_equally():
    candidates = [
        {"stock_code": "A", "industry": "Tech", "pass_filter": 1, "total_score": 0.9},
        {"stock_code": "B", "industry": "Tech", "pass_filter": 1, "total_score": 0.8},
        {"stock_code": "C", "industry": "Tech", "pass_filter": 1, "total_score": 0.7},
        {"stock_code": "D", "industry": "Health", "pass_filter": 1, "total_score": 0.6},
    ]

    selected = select_portfolio(candidates, size=3, max_per_industry=2)

    assert [row["stock_code"] for row in selected] == ["A", "B", "D"]
    assert all(row["weight"] == 1 / 3 for row in selected)
