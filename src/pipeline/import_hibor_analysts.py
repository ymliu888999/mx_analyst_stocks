from __future__ import annotations

from pathlib import Path

from src import db
from src.data_providers.hibor_provider import DEFAULT_HIBOR_URLS, fetch_hibor_analysts
from src.utils.normalize import now_text, stable_id


def import_hibor_analysts(db_path: Path | str, rows: list[dict]) -> int:
    normalized = []
    for row in rows:
        analyst = (row.get("analyst_name") or "").strip()
        broker = (row.get("broker") or "").strip()
        industry = (row.get("industry") or "").strip()
        award_name = row.get("award_name")
        award_year = row.get("award_year")
        rank = row.get("rank")
        if not analyst or not broker or not industry:
            continue
        normalized.append(
            {
                "id": stable_id(analyst, broker, industry, award_name, award_year, rank),
                "analyst_name": analyst,
                "broker": broker,
                "team_name": row.get("team_name") or f"{analyst}团队",
                "industry": industry,
                "award_name": award_name,
                "award_year": int(award_year) if award_year not in (None, "") else None,
                "rank": rank,
                "source_note": row.get("source_note"),
                "active": int(row.get("active") or 1),
                "created_at": now_text(),
                "updated_at": now_text(),
            }
        )
    with db.connect(db_path) as conn:
        return db.upsert_rows(conn, "analyst_awards", normalized)


def fetch_and_import_hibor_analysts(
    db_path: Path | str,
    urls: list[str] | None = None,
) -> dict:
    db.init_db(db_path)
    rows, notes = fetch_hibor_analysts(urls or DEFAULT_HIBOR_URLS)
    imported = import_hibor_analysts(db_path, rows)
    return {"fetched_rows": len(rows), "imported_rows": imported, "notes": notes}
