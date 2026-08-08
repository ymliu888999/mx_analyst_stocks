from __future__ import annotations

from datetime import datetime
from typing import Iterable

from src import db
from src.data_providers import akshare_provider
from src.settings import Settings
from src.utils.logger import get_logger


def _retention_cutoff(reference: datetime, retain_months: int) -> str:
    retain_months = max(int(retain_months or 0), 1)
    year = reference.year
    month = reference.month - (retain_months - 1)
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}{month:02d}01"


def _prune_report_history(conn, retain_months: int, run_date: str) -> dict[str, object]:
    cutoff = _retention_cutoff(datetime.strptime(run_date, "%Y%m%d"), retain_months)
    deleted_reports = conn.execute(
        "delete from research_report where publish_date <> '' and publish_date < ?",
        (cutoff,),
    ).rowcount
    deleted_ratings = conn.execute(
        "delete from research_rating where publish_date <> '' and publish_date < ?",
        (cutoff,),
    ).rowcount
    conn.commit()
    return {
        "cutoff": cutoff,
        "deleted_reports": deleted_reports,
        "deleted_ratings": deleted_ratings,
    }


def refresh_reports(
    db_path,
    rating_map: dict[str, str],
    days: int,
    retain_months: int = 2,
) -> dict:
    logger = get_logger(__name__)
    db.init_db(db_path)
    run_date = datetime.now().strftime("%Y%m%d")
    notes: list[str] = []
    report_rows: list[dict] = []
    rating_rows: list[dict] = []
    try:
        report_rows, rating_rows, notes = akshare_provider.fetch_research_reports(days, rating_map)
    except Exception as exc:
        logger.warning("AKShare report update failed: %s", exc)
        notes.append(f"AKShare report update failed: {exc}")
    with db.connect(db_path) as conn:
        reports = db.upsert_rows(conn, "research_report", report_rows) if report_rows else 0
        ratings = db.upsert_rows(conn, "research_rating", rating_rows) if rating_rows else 0
        retention = _prune_report_history(conn, retain_months, run_date)
        for note in notes:
            db.add_quality(conn, run_date, "research_reports", "akshare", "info" if report_rows else "warning", note)
        db.add_quality(
            conn,
            run_date,
            "research_reports",
            retention["cutoff"],
            "info",
            f"kept reports and ratings from {retain_months} month(s); pruned rows older than {retention['cutoff']}",
        )
    return {"reports": reports, "ratings": ratings, "notes": notes, **retention}


def update_reports(settings: Settings, days: int) -> dict:
    return refresh_reports(
        settings.db_path,
        settings.rating_map,
        days,
        retain_months=int(settings.strategy.get("retain_report_months", 2)),
    )
