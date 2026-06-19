from __future__ import annotations

from datetime import datetime

from src import db
from src.data_providers import akshare_provider
from src.data_providers.tushare_provider import TushareProvider
from src.settings import Settings
from src.utils.logger import get_logger


def update_market(settings: Settings, days: int) -> dict:
    logger = get_logger(__name__)
    db.init_db(settings.db_path)
    run_date = datetime.now().strftime("%Y%m%d")
    max_stocks = int(settings.strategy.get("max_market_update_stocks", 80))
    with db.connect(settings.db_path) as conn:
        stocks = conn.execute(
            "select stock_code from stock_master where list_status='L' order by stock_code limit ?",
            (max_stocks,),
        ).fetchall()
        if not stocks:
            db.add_quality(conn, run_date, "market", 0, "warning", "stock_master is empty; run update-stock-universe first")
            return {"updated_stocks": 0, "bar_rows": 0, "basic_rows": 0}
    provider = TushareProvider(settings.tushare_token) if settings.use_tushare else None
    bar_total = 0
    basic_total = 0
    updated = 0
    with db.connect(settings.db_path) as conn:
        for stock in stocks:
            code = stock["stock_code"]
            notes: list[str] = []
            try:
                if provider:
                    bars, basics, notes = provider.daily_bars(code, days)
                    source = "tushare"
                else:
                    bars, notes = akshare_provider.fetch_daily_bars(code, days)
                    basics = []
                    source = "akshare"
                bar_total += db.upsert_rows(conn, "daily_bar", bars)
                if basics:
                    basic_total += db.upsert_rows(conn, "daily_basic", basics)
                updated += 1
                for note in notes:
                    db.add_quality(conn, run_date, f"market.{code}", source, "info", note)
            except Exception as exc:
                logger.warning("market update failed for %s: %s", code, exc)
                db.add_quality(conn, run_date, f"market.{code}", code, "warning", str(exc))
    return {"updated_stocks": updated, "bar_rows": bar_total, "basic_rows": basic_total}
