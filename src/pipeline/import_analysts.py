from __future__ import annotations

import csv
from pathlib import Path

from src import db
from src.utils.normalize import now_text, stable_id


def import_analysts(db_path: Path | str, csv_path: Path | str) -> int:
    path = Path(csv_path)
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            analyst = (row.get("analyst_name") or "").strip()
            broker = (row.get("broker") or "").strip()
            if not analyst or not broker:
                continue
            rows.append(
                {
                    "id": stable_id(analyst, broker, row.get("team_name"), row.get("industry"), row.get("award_year")),
                    "analyst_name": analyst,
                    "broker": broker,
                    "team_name": row.get("team_name"),
                    "industry": row.get("industry"),
                    "award_name": row.get("award_name"),
                    "award_year": int(row.get("award_year") or 0) or None,
                    "rank": row.get("rank"),
                    "source_note": row.get("source_note"),
                    "active": int(row.get("active") or 1),
                    "created_at": now_text(),
                    "updated_at": now_text(),
                }
            )
    with db.connect(db_path) as conn:
        return db.upsert_rows(conn, "analyst_awards", rows)
