from pathlib import Path

from src import db
from src.dashboard.app import (
    create_analyst,
    delete_analyst,
    get_dashboard_metrics,
    load_analysts,
    load_report_stock_details,
    load_selected_portfolio,
    update_analyst,
)


def test_dashboard_can_create_update_delete_analysts(tmp_path):
    db_path = tmp_path / "strategy.db"
    db.init_db(db_path)

    analyst_id = create_analyst(
        db_path,
        {
            "analyst_name": "Alice",
            "broker": "BrokerA",
            "team_name": "Alice Team",
            "industry": "Tech",
            "award_name": "Award",
            "award_year": 2024,
            "rank": "1",
            "source_note": "manual",
            "active": 1,
        },
    )
    analysts = load_analysts(db_path)
    assert len(analysts) == 1
    assert analysts.iloc[0]["analyst_name"] == "Alice"

    update_analyst(db_path, analyst_id, {"industry": "Semiconductor", "rank": "2"})
    analysts = load_analysts(db_path)
    assert analysts.iloc[0]["industry"] == "Semiconductor"
    assert analysts.iloc[0]["rank"] == "2"

    delete_analyst(db_path, analyst_id)
    analysts = load_analysts(db_path)
    assert analysts.empty


def test_dashboard_report_details_show_price_upside_and_scores(tmp_path):
    db_path = tmp_path / "strategy.db"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        conn.execute(
            """insert into stock_master
            (stock_code, stock_name, industry, list_status, is_st, updated_at)
            values ('000001', 'Stock A', 'Tech', 'L', 0, 'now')"""
        )
        conn.execute(
            """insert into daily_bar
            (stock_code, trade_date, close, amount, source, updated_at)
            values ('000001', '20260618', 10, 200000000, 'test', 'now')"""
        )
        conn.execute(
            """insert into research_rating
            (id, stock_code, stock_name, publish_date, broker, analyst_raw, rating,
            normalized_rating, target_price, source, created_at, updated_at)
            values ('r1', '000001', 'Stock A', '20260618', 'BrokerA', 'Alice',
            '买入', 'buy', 15, 'test', 'now', 'now')"""
        )
        conn.execute(
            """insert into weekly_candidate
            (id, run_date, stock_code, stock_name, industry, latest_close, target_price,
            target_upside, effective_star_analyst_count, effective_broker_count,
            upside_score, consensus_score, target_revision_score,
            earnings_revision_score, price_reaction_score, trend_score, total_score,
            rank, pass_filter, fail_reason, created_at)
            values ('c1', '20260619', '000001', 'Stock A', 'Tech', 10, 15,
            0.5, 1, 1, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
            1, 0, 'reject: demo', 'now')"""
        )
        conn.execute(
            """insert into portfolio_suggestion
            (id, run_date, stock_code, stock_name, industry, weight, rank,
            total_score, target_upside, reason, created_at)
            values ('p1', '20260619', '000001', 'Stock A', 'Tech', 0.125,
            1, 0.5, 0.5, 'research_fallback', 'now')"""
        )
        conn.commit()

    details = load_report_stock_details(db_path)
    portfolio = load_selected_portfolio(db_path)

    assert details.iloc[0]["analyst_raw"] == "Alice"
    assert details.iloc[0]["latest_close"] == 10
    assert details.iloc[0]["target_upside"] == 0.5
    assert details.iloc[0]["total_score"] == 0.5
    assert portfolio.iloc[0]["weight"] == 0.125


def test_dashboard_metrics_include_latest_run_time_and_distinct_analysts(tmp_path):
    db_path = tmp_path / "strategy.db"
    db.init_db(db_path)
    analyst_id = create_analyst(
        db_path,
        {
            "analyst_name": "Alice",
            "broker": "BrokerA",
            "team_name": "Alice Team",
            "industry": "Tech",
            "award_name": "Award",
            "award_year": 2024,
            "rank": "1",
            "source_note": "manual",
            "active": 1,
        },
    )
    create_analyst(
        db_path,
        {
            "analyst_name": "Alice",
            "broker": "BrokerA",
            "team_name": "Alice Team",
            "industry": "Semiconductor",
            "award_name": "Award",
            "award_year": 2025,
            "rank": "1",
            "source_note": "manual",
            "active": 1,
        },
    )
    with db.connect(db_path) as conn:
        conn.execute(
            """insert into weekly_candidate
            (id, run_date, stock_code, stock_name, rank, pass_filter, created_at)
            values ('c1', '20260619', '000001', 'Stock A', 1, 0, '2026-06-19 15:30:00')"""
        )
        conn.commit()

    metrics = get_dashboard_metrics(db_path)

    assert metrics["latest_run_time"] == "2026-06-19 15:30:00"
    assert metrics["distinct_analyst_count"] == 1
    assert analyst_id


def test_dashboard_source_keeps_chinese_labels_intact():
    source = (Path(__file__).parents[1] / "src" / "dashboard" / "app.py").read_text(encoding="utf-8")

    assert "明星分析师共识策略" in source
    assert "人工刷新" in source
    assert "历史记录" in source
    assert "最新运行时间" in source
    assert "最终组合" in source
    assert "????" not in source
