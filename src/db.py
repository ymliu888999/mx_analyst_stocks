from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from src.utils.normalize import now_text, stable_id


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS stock_master (
        stock_code TEXT PRIMARY KEY, ts_code TEXT, stock_name TEXT, exchange TEXT,
        list_date TEXT, delist_date TEXT, industry TEXT, list_status TEXT,
        is_st INTEGER DEFAULT 0, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS daily_bar (
        stock_code TEXT, trade_date TEXT, open REAL, high REAL, low REAL, close REAL,
        pre_close REAL, volume REAL, amount REAL, adj_factor REAL, source TEXT,
        updated_at TEXT, PRIMARY KEY (stock_code, trade_date))""",
    """CREATE TABLE IF NOT EXISTS daily_basic (
        stock_code TEXT, trade_date TEXT, close REAL, turnover_rate REAL,
        volume_ratio REAL, pe REAL, pe_ttm REAL, pb REAL, ps REAL, total_mv REAL,
        circ_mv REAL, source TEXT, updated_at TEXT, PRIMARY KEY (stock_code, trade_date))""",
    """CREATE TABLE IF NOT EXISTS research_rating (
        id TEXT PRIMARY KEY, stock_code TEXT, stock_name TEXT, publish_date TEXT,
        broker TEXT, analyst_raw TEXT, rating TEXT, normalized_rating TEXT,
        rating_change TEXT, previous_rating TEXT, target_price_low REAL,
        target_price_high REAL, target_price REAL, source TEXT, source_url TEXT,
        created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS research_report (
        id TEXT PRIMARY KEY, stock_code TEXT, stock_name TEXT, report_title TEXT,
        broker TEXT, rating TEXT, normalized_rating TEXT, report_count_1m INTEGER,
        eps_y0 REAL, eps_y1 REAL, eps_y2 REAL, pe_y0 REAL, pe_y1 REAL, pe_y2 REAL,
        industry TEXT, publish_date TEXT, pdf_url TEXT, source TEXT, created_at TEXT,
        updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS profit_forecast_snapshot (
        id TEXT PRIMARY KEY, snapshot_date TEXT, stock_code TEXT, stock_name TEXT,
        source TEXT, report_count INTEGER, buy_count REAL, overweight_count REAL,
        neutral_count REAL, underweight_count REAL, sell_count REAL, eps_year_0 REAL,
        eps_year_1 REAL, eps_year_2 REAL, np_year_0 REAL, np_year_1 REAL,
        np_year_2 REAL, institution_count INTEGER, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS analyst_awards (
        id TEXT PRIMARY KEY, analyst_name TEXT, broker TEXT, team_name TEXT,
        industry TEXT, award_name TEXT, award_year INTEGER, rank TEXT,
        source_note TEXT, active INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS risk_event (
        id TEXT PRIMARY KEY, stock_code TEXT, stock_name TEXT, event_date TEXT,
        event_type TEXT, title TEXT, url TEXT, severity TEXT, keyword_hit TEXT,
        source TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS weekly_candidate (
        id TEXT PRIMARY KEY, run_date TEXT, stock_code TEXT, stock_name TEXT,
        industry TEXT, latest_close REAL, target_price REAL, target_upside REAL,
        effective_star_analyst_count INTEGER, effective_broker_count INTEGER,
        target_price_revision REAL, earnings_revision REAL, post_report_return REAL,
        trend_score REAL, risk_penalty REAL, upside_score REAL, consensus_score REAL,
        target_revision_score REAL, earnings_revision_score REAL,
        price_reaction_score REAL, total_score REAL, rank INTEGER, pass_filter INTEGER,
        fail_reason TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS portfolio_suggestion (
        id TEXT PRIMARY KEY, run_date TEXT, stock_code TEXT, stock_name TEXT,
        industry TEXT, weight REAL, rank INTEGER, total_score REAL,
        target_upside REAL, reason TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS data_quality_report (
        id TEXT PRIMARY KEY, run_date TEXT, item TEXT, value TEXT, severity TEXT,
        message TEXT, created_at TEXT)""",
]


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str) -> None:
    with connect(db_path) as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


def upsert_rows(conn: sqlite3.Connection, table: str, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        keys = list(row.keys())
        placeholders = ",".join("?" for _ in keys)
        columns = ",".join(keys)
        updates = ",".join(f"{k}=excluded.{k}" for k in keys if k != "id")
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON CONFLICT DO UPDATE SET {updates}"
        conn.execute(sql, [row[k] for k in keys])
        count += 1
    conn.commit()
    return count


def add_quality(
    conn: sqlite3.Connection,
    run_date: str,
    item: str,
    value: object,
    severity: str,
    message: str,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO data_quality_report
        (id, run_date, item, value, severity, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (stable_id(run_date, item, message), run_date, item, str(value), severity, message, now_text()),
    )
    conn.commit()
