from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src import db
from src.data_providers.akshare_provider import fetch_latest_quotes
from src.settings import ROOT, load_yaml
from src.pipeline.update_reports import refresh_reports
from src.strategy.factors import (
    compute_post_report_return,
    compute_target_revision,
    compute_target_upside,
    compute_trend_score,
)
from src.strategy.filters import evaluate_candidate
from src.strategy.portfolio import select_portfolio
from src.strategy.scorer import score_candidate
from src.utils.normalize import now_text, stable_id


def _market_metrics(conn) -> dict[str, dict]:
    rows = conn.execute(
        """select stock_code, trade_date, close, amount
        from daily_bar
        order by stock_code, trade_date"""
    ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["stock_code"], []).append(dict(row))

    metrics: dict[str, dict] = {}
    for code, items in grouped.items():
        closes = [row["close"] for row in items if row["close"] is not None]
        amounts = [row["amount"] for row in items if row["amount"] is not None]
        latest = closes[-1] if closes else None
        metrics[code] = {
            "latest_close": latest,
            "ma20": sum(closes[-20:]) / min(len(closes), 20) if closes else None,
            "ma60": sum(closes[-60:]) / min(len(closes), 60) if closes else None,
            "avg_amount_20d": sum(amounts[-20:]) / min(len(amounts), 20) if amounts else None,
            "return_20d": latest / closes[-21] - 1 if latest is not None and len(closes) > 20 and closes[-21] else None,
            "return_60d": latest / closes[-61] - 1 if latest is not None and len(closes) > 60 and closes[-61] else None,
        }
    return metrics


def _star_analyst_index(conn) -> set[tuple[str, str]]:
    rows = conn.execute(
        "select analyst_name, broker from analyst_awards where active=1"
    ).fetchall()
    return {
        ((row["analyst_name"] or "").strip(), (row["broker"] or "").strip())
        for row in rows
        if row["analyst_name"] and row["broker"]
    }


def _star_match_count(reports: list[dict], star_index: set[tuple[str, str]]) -> tuple[int, bool]:
    matched: set[tuple[str, str]] = set()
    uncertain = False
    for row in reports:
        broker = (row.get("broker") or "").strip()
        analyst_raw = (row.get("analyst_raw") or "").strip()
        names = [
            part.strip()
            for part in analyst_raw.replace("，", ",").split(",")
            if part.strip()
        ]
        for analyst, star_broker in star_index:
            if analyst in names and broker == star_broker:
                matched.add((analyst, broker))
            elif analyst in names:
                uncertain = True
    return len(matched), uncertain


def _close_before_first_report(conn, stock_code: str, publish_date: str | None) -> float | None:
    if not publish_date:
        return None
    row = conn.execute(
        """select close from daily_bar
        where stock_code=? and trade_date <= ?
        order by trade_date desc limit 1""",
        (stock_code, publish_date),
    ).fetchone()
    return row["close"] if row else None


def _previous_target(conn, stock_code: str, before_date: str | None) -> float | None:
    if not before_date:
        return None
    row = conn.execute(
        """select target_price from research_rating
        where stock_code=? and publish_date < ? and target_price is not null
        order by publish_date desc limit 1""",
        (stock_code, before_date),
    ).fetchone()
    return row["target_price"] if row else None


def _build_candidates(conn, run_date: str, config: dict) -> list[dict]:
    market_metrics = _market_metrics(conn)
    star_index = _star_analyst_index(conn)
    reports = conn.execute(
        """select r.stock_code, coalesce(r.stock_name, s.stock_name) stock_name,
        coalesce(s.industry, rr.industry) industry, s.is_st,
        max(r.target_price) target_price,
        min(r.publish_date) first_publish_date,
        max(r.publish_date) latest_publish_date,
        count(distinct r.broker) broker_count,
        count(*) report_count
        from research_rating r
        left join stock_master s on s.stock_code=r.stock_code
        left join research_report rr on rr.stock_code=r.stock_code
        where r.normalized_rating in ('buy','overweight')
        group by r.stock_code"""
    ).fetchall()

    rows: list[dict] = []
    for item in reports:
        code = item["stock_code"]
        market = market_metrics.get(code, {})
        latest = market.get("latest_close")
        target = item["target_price"]
        detail_rows = [
            dict(row)
            for row in conn.execute(
                """select broker, analyst_raw from research_rating
                where stock_code=? and normalized_rating in ('buy','overweight')""",
                (code,),
            ).fetchall()
        ]
        star_count, uncertain = _star_match_count(detail_rows, star_index)
        first_publish = item["first_publish_date"]
        previous_target = _previous_target(conn, code, first_publish)
        close_before_report = _close_before_first_report(conn, code, first_publish)
        candidate = {
            "stock_code": code,
            "stock_name": item["stock_name"],
            "industry": item["industry"],
            "is_st": item["is_st"],
            "listing_days": None,
            "avg_amount_20d": market.get("avg_amount_20d"),
            "effective_broker_count": item["broker_count"],
            "effective_star_analyst_count": star_count,
            "target_upside": compute_target_upside(latest, target),
            "post_report_return": compute_post_report_return(latest, close_before_report),
            "return_20d": market.get("return_20d"),
            "return_60d": market.get("return_60d"),
            "latest_close": latest,
            "ma60": market.get("ma60"),
            "has_severe_risk": False,
            "has_medium_risk": False,
            "uncertain_match": uncertain,
            "target_price_revision": compute_target_revision(target, previous_target),
            "earnings_revision": None,
            "trend_score": compute_trend_score(latest, market.get("ma20"), market.get("ma60")),
            "risk_penalty": 0.0,
        }
        filtered = evaluate_candidate(candidate, config)
        scored = score_candidate(candidate, config)
        reason = filtered.explanation
        if filtered.pass_filter:
            reason = "pass: rating buy/overweight, target upside, star consensus, liquidity and price reaction filters"
        rows.append(
            {
                "id": stable_id(run_date, code),
                "run_date": run_date,
                "stock_code": code,
                "stock_name": item["stock_name"],
                "industry": item["industry"],
                "latest_close": latest,
                "target_price": target,
                "target_upside": scored["target_upside"],
                "effective_star_analyst_count": star_count,
                "effective_broker_count": item["broker_count"],
                "target_price_revision": scored["target_price_revision"],
                "earnings_revision": scored["earnings_revision"],
                "post_report_return": scored["post_report_return"],
                "trend_score": scored["trend_score"],
                "risk_penalty": scored["risk_penalty"],
                "upside_score": scored["upside_score"],
                "consensus_score": scored["consensus_score"],
                "target_revision_score": scored["target_revision_score"],
                "earnings_revision_score": scored["earnings_revision_score"],
                "price_reaction_score": scored["price_reaction_score"],
                "total_score": scored["total_score"],
                "rank": 0,
                "pass_filter": 1 if filtered.pass_filter else 0,
                "fail_reason": reason,
                "created_at": now_text(),
            }
        )
    rows.sort(key=lambda x: x["total_score"] or 0, reverse=True)
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx
    return rows


def _refresh_latest_quotes(conn, run_date: str) -> None:
    codes = [
        row["stock_code"]
        for row in conn.execute(
            "select distinct stock_code from research_rating where stock_code is not null"
        ).fetchall()
    ]
    if not codes:
        return
    try:
        quote_rows, notes = fetch_latest_quotes(codes)
        if quote_rows:
            db.upsert_rows(conn, "daily_bar", quote_rows)
        for note in notes:
            db.add_quality(conn, run_date, "latest_quotes", len(quote_rows), "info", note)
    except Exception as exc:
        db.add_quality(conn, run_date, "latest_quotes", 0, "warning", f"latest quote refresh failed: {exc}")


def _portfolio_rows(run_date: str, candidates: list[dict], config: dict) -> list[dict]:
    fallback = False
    selected = select_portfolio(
        candidates,
        size=int(config.get("portfolio_size", 8)),
        max_per_industry=int(config.get("max_per_industry", 2)),
    )
    if not selected and config.get("allow_research_portfolio_fallback", True):
        fallback = True
        selected = [
            {**row}
            for row in sorted(
            candidates,
            key=lambda row: row.get("total_score") or 0,
            reverse=True,
            )[: int(config.get("portfolio_size", 8))]
        ]
        if selected:
            weight = 1 / int(config.get("portfolio_size", 8))
            for idx, row in enumerate(selected, 1):
                row["rank"] = idx
                row["weight"] = weight
    elif selected:
        weight = 1 / int(config.get("portfolio_size", 8))
        for row in selected:
            row["weight"] = weight
    rows = []
    for row in selected:
        reason = row.get("fail_reason")
        if fallback:
            reason = f"research_fallback: strict filters not passed; {reason}"
        rows.append(
            {
                "id": stable_id(run_date, "portfolio", row["stock_code"]),
                "run_date": run_date,
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name"),
                "industry": row.get("industry"),
                "weight": row.get("weight"),
                "rank": row.get("rank"),
                "total_score": row.get("total_score"),
                "target_upside": row.get("target_upside"),
                "reason": reason,
                "created_at": now_text(),
            }
        )
    return rows


def _write_reports(
    output_dir: Path,
    run_date: str,
    candidates: list[dict],
    portfolio: list[dict],
    quality: list[dict],
) -> dict[str, str]:
    weekly_dir = output_dir / "weekly" / run_date
    weekly_dir.mkdir(parents=True, exist_ok=True)
    candidate_df = pd.DataFrame(candidates)
    portfolio_df = pd.DataFrame(portfolio)
    top20 = candidate_df.head(20) if not candidate_df.empty else candidate_df
    csv_path = weekly_dir / "candidates_top20.csv"
    portfolio_csv_path = weekly_dir / "portfolio_suggestion.csv"
    excel_path = weekly_dir / "weekly_report.xlsx"
    md_path = weekly_dir / "weekly_report.md"
    top20.to_csv(csv_path, index=False, encoding="utf-8-sig")
    portfolio_df.to_csv(portfolio_csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        top20.to_excel(writer, sheet_name="Top20候选池", index=False)
        portfolio_df.to_excel(writer, sheet_name="建议组合", index=False)
        pd.DataFrame(quality).to_excel(writer, sheet_name="数据质量", index=False)

    lines = [f"# 明星分析师预期上修共识策略周报 {run_date}", "", "## Top20候选池", ""]
    if top20.empty:
        lines.append("暂无候选股票。请检查股票、行情、研报和目标价数据覆盖情况。")
    else:
        lines.append(top20.to_markdown(index=False))
    lines.extend(["", "## 建议组合", ""])
    if portfolio_df.empty:
        lines.append("暂无通过全部硬过滤的建议组合。")
    else:
        lines.append(portfolio_df.to_markdown(index=False))
    lines.extend(["", "## 数据质量报告", ""])
    if quality:
        lines.append(pd.DataFrame(quality).to_markdown(index=False))
    else:
        lines.append("未记录明显数据质量问题。")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "portfolio_csv_path": str(portfolio_csv_path),
        "excel_path": str(excel_path),
    }


def run_weekly(
    db_path: Path | str,
    output_dir: Path | str = "outputs",
    config: dict | None = None,
) -> dict:
    run_date = datetime.now().strftime("%Y%m%d")
    config = config or load_yaml(ROOT / "config" / "strategy.yaml")
    db.init_db(db_path)
    if config.get("refresh_reports_on_run", True):
        refresh_reports(
            db_path,
            load_yaml(ROOT / "config" / "rating_map.yaml"),
            int(config.get("report_fetch_days", 90)),
            int(config.get("retain_report_months", 2)),
        )
    with db.connect(db_path) as conn:
        if config.get("refresh_latest_quotes", True):
            _refresh_latest_quotes(conn, run_date)
        candidates = _build_candidates(conn, run_date, config)
        portfolios = _portfolio_rows(run_date, candidates, config)
        conn.execute("delete from weekly_candidate where run_date=?", (run_date,))
        conn.execute("delete from portfolio_suggestion where run_date=?", (run_date,))
        if candidates:
            db.upsert_rows(conn, "weekly_candidate", candidates)
        if portfolios:
            db.upsert_rows(conn, "portfolio_suggestion", portfolios)
        if not candidates:
            db.add_quality(
                conn,
                run_date,
                "weekly_candidate",
                0,
                "warning",
                "No candidates generated; missing ratings, prices, or target prices",
            )
        quality = [
            dict(r)
            for r in conn.execute(
                "select item,value,severity,message from data_quality_report where run_date=?",
                (run_date,),
            ).fetchall()
        ]
    paths = _write_reports(Path(output_dir), run_date, candidates[:20], portfolios, quality)
    return {
        "run_date": run_date,
        "candidate_count": len(candidates),
        "portfolio_count": len(portfolios),
        **paths,
    }
