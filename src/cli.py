from __future__ import annotations

import argparse
from pathlib import Path

from src import db
from src.pipeline.import_analysts import import_analysts
from src.pipeline.import_hibor_analysts import fetch_and_import_hibor_analysts
from src.pipeline.update_market_data import update_market
from src.pipeline.update_reports import update_reports
from src.pipeline.update_stock_universe import update_stock_universe
from src.pipeline.weekly_run import run_weekly
from src.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyst-consensus-strategy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    import_cmd = sub.add_parser("import-analysts")
    import_cmd.add_argument("--file", default="data/manual/analyst_awards_seed.csv")
    hibor_cmd = sub.add_parser("fetch-hibor-analysts")
    hibor_cmd.add_argument("--url", action="append", default=None)
    sub.add_parser("update-stock-universe")
    market = sub.add_parser("update-market")
    market.add_argument("--days", type=int, default=180)
    reports = sub.add_parser("update-reports")
    reports.add_argument("--days", type=int, default=90)
    sub.add_parser("weekly-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    args = build_parser().parse_args(argv)
    if args.command == "init-db":
        db.init_db(settings.db_path)
        print(f"database initialized: {settings.db_path}")
    elif args.command == "import-analysts":
        count = import_analysts(settings.db_path, Path(args.file))
        print(f"analysts imported: {count}")
    elif args.command == "fetch-hibor-analysts":
        print(fetch_and_import_hibor_analysts(settings.db_path, args.url))
    elif args.command == "update-stock-universe":
        print(update_stock_universe(settings))
    elif args.command == "update-market":
        print(update_market(settings, args.days))
    elif args.command == "update-reports":
        print(update_reports(settings, args.days))
    elif args.command == "weekly-run":
        print(run_weekly(settings.db_path, settings.root / "outputs"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
