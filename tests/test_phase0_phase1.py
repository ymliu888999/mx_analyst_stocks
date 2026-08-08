import csv
import sqlite3
from pathlib import Path

from src import db
from src.data_providers.akshare_provider import parse_cninfo_forecast_frame
from src.pipeline.import_analysts import import_analysts
from src.pipeline.update_reports import refresh_reports
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

    result = run_weekly(
        db_path,
        output_dir=output_dir,
        config={"refresh_reports_on_run": False, "refresh_latest_quotes": False},
    )

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


def test_refresh_reports_keeps_recent_two_months_only(tmp_path, monkeypatch):
    db_path = tmp_path / "strategy.db"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        conn.execute(
            """insert into research_report
            (id, stock_code, stock_name, report_title, broker, rating, normalized_rating,
            report_count_1m, eps_y0, eps_y1, eps_y2, pe_y0, pe_y1, pe_y2, industry,
            publish_date, pdf_url, source, created_at, updated_at)
            values ('old-report', '000001', 'Old Stock', 'Old Report', 'Old Broker', 'buy', 'buy',
            null, null, null, null, null, null, null, null, '20260618', '', 'seed', 'now', 'now')"""
        )
        conn.execute(
            """insert into research_rating
            (id, stock_code, stock_name, publish_date, broker, analyst_raw, rating,
            normalized_rating, rating_change, previous_rating, target_price_low,
            target_price_high, target_price, source, source_url, created_at, updated_at)
            values ('old-rating', '000001', 'Old Stock', '20260618', 'Old Broker', 'Alice',
            'buy', 'buy', null, null, null, null, 10, 'seed', '', 'now', 'now')"""
        )
        conn.commit()

    def fake_fetch(days, rating_map):
        assert days == 90
        assert rating_map["买入"] == "buy"
        report_rows = [
            {
                "id": "report-20260731",
                "stock_code": "000002",
                "stock_name": "July Stock",
                "report_title": "July Report",
                "broker": "BrokerA",
                "rating": "买入",
                "normalized_rating": "buy",
                "report_count_1m": None,
                "eps_y0": None,
                "eps_y1": None,
                "eps_y2": None,
                "pe_y0": None,
                "pe_y1": None,
                "pe_y2": None,
                "industry": None,
                "publish_date": "20260731",
                "pdf_url": "",
                "source": "fake",
                "created_at": "now",
                "updated_at": "now",
            },
            {
                "id": "report-20260807",
                "stock_code": "000003",
                "stock_name": "August Stock",
                "report_title": "August Report",
                "broker": "BrokerB",
                "rating": "买入",
                "normalized_rating": "buy",
                "report_count_1m": None,
                "eps_y0": None,
                "eps_y1": None,
                "eps_y2": None,
                "pe_y0": None,
                "pe_y1": None,
                "pe_y2": None,
                "industry": None,
                "publish_date": "20260807",
                "pdf_url": "",
                "source": "fake",
                "created_at": "now",
                "updated_at": "now",
            },
        ]
        rating_rows = [
            {
                "id": "rating-20260731",
                "stock_code": "000002",
                "stock_name": "July Stock",
                "publish_date": "20260731",
                "broker": "BrokerA",
                "analyst_raw": "Alice",
                "rating": "买入",
                "normalized_rating": "buy",
                "rating_change": None,
                "previous_rating": None,
                "target_price_low": None,
                "target_price_high": None,
                "target_price": 12,
                "source": "fake",
                "source_url": "",
                "created_at": "now",
                "updated_at": "now",
            },
            {
                "id": "rating-20260807",
                "stock_code": "000003",
                "stock_name": "August Stock",
                "publish_date": "20260807",
                "broker": "BrokerB",
                "analyst_raw": "Bob",
                "rating": "买入",
                "normalized_rating": "buy",
                "rating_change": None,
                "previous_rating": None,
                "target_price_low": None,
                "target_price_high": None,
                "target_price": 13,
                "source": "fake",
                "source_url": "",
                "created_at": "now",
                "updated_at": "now",
            },
        ]
        return report_rows, rating_rows, ["fake note"]

    monkeypatch.setattr("src.data_providers.akshare_provider.fetch_research_reports", fake_fetch)

    result = refresh_reports(db_path, {"买入": "buy"}, days=90, retain_months=2)

    assert result["reports"] == 2
    assert result["ratings"] == 2
    assert result["cutoff"] == "20260701"
    with sqlite3.connect(db_path) as conn:
        june_count = conn.execute(
            "select count(*) from research_rating where publish_date='20260618'"
        ).fetchone()[0]
        july_count = conn.execute(
            "select count(*) from research_rating where publish_date='20260731'"
        ).fetchone()[0]
        aug_count = conn.execute(
            "select count(*) from research_rating where publish_date='20260807'"
        ).fetchone()[0]
    assert june_count == 0
    assert july_count == 1
    assert aug_count == 1
