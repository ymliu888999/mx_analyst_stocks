from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src import db
from src.data_providers import akshare_provider
from src.data_providers.tushare_provider import TushareProvider
from src.settings import Settings
from src.utils.logger import get_logger


def update_stock_universe(settings: Settings, db_path: Path | str | None = None) -> dict:
    logger = get_logger(__name__)
    db_path = db_path or settings.db_path
    db.init_db(db_path)
    run_date = datetime.now().strftime("%Y%m%d")
    notes: list[str] = []
    rows = []
    source = "none"
    if settings.use_tushare:
        try:
            rows, notes = TushareProvider(settings.tushare_token).stock_universe()
            source = "tushare"
        except Exception as exc:
            notes.append(f"Tushare stock universe failed, fallback to AKShare: {exc}")
            logger.warning("Tushare stock universe failed: %s", exc)
    if not rows and settings.use_akshare:
        try:
            rows, ak_notes = akshare_provider.fetch_stock_universe()
            notes.extend(ak_notes)
            source = "akshare"
        except Exception as exc:
            notes.append(f"AKShare stock universe failed: {exc}")
            logger.warning("AKShare stock universe failed: %s", exc)
    with db.connect(db_path) as conn:
        count = db.upsert_rows(conn, "stock_master", rows) if rows else 0
        for note in notes:
            db.add_quality(conn, run_date, "stock_universe", source, "info" if rows else "error", note)
    return {"source": source, "count": count, "notes": notes}
