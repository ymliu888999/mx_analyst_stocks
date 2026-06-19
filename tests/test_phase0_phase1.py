import csv
import sqlite3
from pathlib import Path

from src import db
from src.data_providers.akshare_provider import parse_cninfo_forecast_frame
from src.pipeline.import_analysts import import_analysts
from src.pipeline.weekly_run import run_weekly


def test_init_db_creates_required_tables(tmp_path):
    db_path = tmp_path / "strategy.db"

    db.init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            ).fetchall()
        }
    assert "stock_master" in tables
    assert "daily_bar" in tables
    assert "research_rating" in tables
    assert "analyst_awards" in tables
    assert "data_quality_report" in tables


def test_import_analysts_upserts_manual_csv(tmp_path):
    db_path = tmp_path / "strategy.db"
    csv_path = tmp_path / "analysts.csv"
    db.init_db(db_path)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "analyst_name",
                "broker",
                "team_name",
                "industry",
                "award_name",
                "award_year",
                "rank",
                "source_note",
                "active",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analyst_name": "张三",
                "broker": "示例证券",
                "team_name": "张三团队",
                "industry": "电子",
                "award_name": "新财富",
                "award_year": "2024",
                "rank": "1",
                "source_note": "测试",
                "active": "1",
            }
        )

    count = import_analysts(db_path, csv_path)

    assert count == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select analyst_name, broker, active from analyst_awards"
        ).fetchone()
    assert row == ("张三", "示例证券", 1)


def test_weekly_run_outputs_quality_report_when_data_missing(tmp_path):
    db_path = tmp_path / "strategy.db"
    output_dir = tmp_path / "outputs"
    db.init_db(db_path)

    result = run_weekly(db_path, output_dir=output_dir)

    assert result["candidate_count"] == 0
    assert Path(result["markdown_path"]).exists()
    assert Path(result["csv_path"]).exists()
    assert Path(result["excel_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        quality_count = conn.execute(
            "select count(*) from data_quality_report"
        ).fetchone()[0]
    assert quality_count >= 1


def test_parse_cninfo_forecast_frame_maps_rating_and_target_price():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "证券代码": "000001",
                "证券简称": "平安银行",
                "发布日期": "2026-06-18",
                "研究机构名称": "示例证券",
                "研究员名称": "张三",
                "投资评级": "买入",
                "评级变化": "维持",
                "前一次投资评级": "买入",
                "目标价格-下限": 10,
                "目标价格-上限": 12,
            }
        ]
    )

    reports, ratings = parse_cninfo_forecast_frame(frame, {"买入": "buy"})

    assert reports[0]["stock_code"] == "000001"
    assert reports[0]["source"] == "akshare.stock_rank_forecast_cninfo"
    assert ratings[0]["normalized_rating"] == "buy"
    assert ratings[0]["target_price"] == 11
