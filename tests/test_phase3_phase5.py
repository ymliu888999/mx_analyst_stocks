import sqlite3
from pathlib import Path

from src import db
from src.pipeline.weekly_run import run_weekly


def _seed_candidate_inputs(db_path: Path, count: int = 10) -> None:
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        for idx in range(count):
            code = f"000{idx + 1:03d}"
            conn.execute(
                """insert into stock_master
                (stock_code, ts_code, stock_name, exchange, industry, list_status, is_st, updated_at)
                values (?, ?, ?, 'SZ', ?, 'L', 0, '2026-06-19')""",
                (code, f"{code}.SZ", f"Stock{idx + 1}", "Tech" if idx < 6 else "Health"),
            )
            conn.execute(
                """insert into daily_bar
                (stock_code, trade_date, open, high, low, close, amount, source, updated_at)
                values (?, '20260618', 9, 11, 8, 10, 200000000, 'test', '2026-06-19')""",
                (code,),
            )
            for broker in ["BrokerA", "BrokerB"]:
                report_id = f"{code}-{broker}"
                conn.execute(
                    """insert into research_rating
                    (id, stock_code, stock_name, publish_date, broker, analyst_raw, rating,
                    normalized_rating, target_price, source, created_at, updated_at)
                    values (?, ?, ?, '20260618', ?, 'AnalystX', '买入', 'buy', 15,
                    'test', '2026-06-19', '2026-06-19')""",
                    (report_id, code, f"Stock{idx + 1}", broker),
                )
        conn.commit()


def test_weekly_run_writes_top20_and_research_fallback_portfolio(tmp_path):
    db_path = tmp_path / "strategy.db"
    output_dir = tmp_path / "outputs"
    _seed_candidate_inputs(db_path)

    result = run_weekly(
        db_path,
        output_dir=output_dir,
        config={
            "portfolio_size": 8,
            "max_per_industry": 8,
            "allow_research_portfolio_fallback": True,
            "refresh_latest_quotes": False,
            "min_target_upside": 0.25,
            "max_target_upside": 1.0,
            "min_avg_amount_20d": 150000000,
            "weights": {
                "target_upside": 0.25,
                "star_consensus": 0.20,
                "target_revision": 0.20,
                "earnings_revision": 0.15,
                "price_reaction": 0.10,
                "trend": 0.10,
            },
        },
    )

    assert result["candidate_count"] == 10
    assert result["portfolio_count"] == 8
    assert Path(result["markdown_path"]).read_text(encoding="utf-8").find("建议组合") > 0
    assert Path(result["csv_path"]).exists()
    assert Path(result["portfolio_csv_path"]).exists()
    assert Path(result["excel_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        reasons = [
            row[0]
            for row in conn.execute("select reason from portfolio_suggestion order by rank").fetchall()
        ]
    assert len(reasons) == 8
    assert all("research_fallback" in reason for reason in reasons)
    with sqlite3.connect(db_path) as conn:
        weights = [
            row[0]
            for row in conn.execute(
                "select weight from portfolio_suggestion order by rank"
            ).fetchall()
        ]
    assert weights == [0.125] * 8


def test_dashboard_loads_latest_weekly_tables(tmp_path):
    db_path = tmp_path / "strategy.db"
    _seed_candidate_inputs(db_path)
    run_weekly(
        db_path,
        output_dir=tmp_path / "outputs",
        config={"allow_research_portfolio_fallback": True, "refresh_latest_quotes": False},
    )

    from src.dashboard.app import load_latest_weekly_tables

    tables = load_latest_weekly_tables(db_path)

    assert tables["run_date"]
    assert len(tables["candidates"]) == 10
    assert len(tables["portfolio"]) > 0
