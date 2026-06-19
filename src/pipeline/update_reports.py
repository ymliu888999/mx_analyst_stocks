from __future__ import annotations

from datetime import datetime

from src import db
from src.data_providers import akshare_provider
from src.settings import Settings
from src.utils.logger import get_logger


def update_reports(settings: Settings, days: int) -> dict:
    logger = get_logger(__name__)
    db.init_db(settings.db_path)
    run_date = datetime.now().strftime("%Y%m%d")
    notes: list[str] = []
    report_rows: list[dict] = []
    rating_rows: list[dict] = []
    try:
        report_rows, rating_rows, notes = akshare_provider.fetch_research_reports(days, settings.rating_map)
        max_rows = int(settings.strategy.get("max_report_rows", 500))
        report_rows = report_rows[:max_rows]
        rating_rows = rating_rows[:max_rows]
    except Exception as exc:
        logger.warning("AKShare report update failed: %s", exc)
        notes.append(f"AKShare report update failed: {exc}")
    with db.connect(settings.db_path) as conn:
        reports = db.upsert_rows(conn, "research_report", report_rows) if report_rows else 0
        ratings = db.upsert_rows(conn, "research_rating", rating_rows) if rating_rows else 0
        for note in notes:
            db.add_quality(conn, run_date, "research_reports", "akshare", "info" if report_rows else "warning", note)
    return {"reports": reports, "ratings": ratings, "notes": notes}
