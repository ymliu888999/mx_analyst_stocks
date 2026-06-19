from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from src.utils.codes import normalize_stock_code, to_ts_code
from src.utils.normalize import as_float, now_text, stable_id


def _import_akshare():
    import akshare as ak

    return ak


def _pick(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return None


def _pick_by_names_or_pos(row: pd.Series, names: list[str], pos: int) -> Any:
    value = _pick(row, names)
    if value is not None:
        return value
    try:
        return row.iloc[pos]
    except IndexError:
        return None


def fetch_stock_universe() -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    ak = _import_akshare()
    try:
        frame = ak.stock_info_a_code_name()
        notes.append(f"AKShare stock_info_a_code_name columns={list(frame.columns)}")
    except Exception as exc:
        notes.append(f"stock_info_a_code_name failed: {exc}")
        frame = ak.stock_zh_a_spot_em()
        notes.append(f"AKShare stock_zh_a_spot_em columns={list(frame.columns)}")
    rows = []
    for _, row in frame.iterrows():
        code = normalize_stock_code(_pick(row, ["code", "代码", "证券代码"]))
        if not code:
            continue
        name = str(_pick(row, ["name", "名称", "证券简称"]) or "")
        rows.append(
            {
                "stock_code": code,
                "ts_code": to_ts_code(code),
                "stock_name": name,
                "exchange": "SH" if code.startswith(("6", "9")) else "SZ",
                "list_date": None,
                "delist_date": None,
                "industry": _pick(row, ["行业", "所属行业"]),
                "list_status": "L",
                "is_st": 1 if "ST" in name.upper() else 0,
                "updated_at": now_text(),
            }
        )
    return rows, notes


def fetch_daily_bars(stock_code: str, days: int) -> tuple[list[dict], list[str]]:
    ak = _import_akshare()
    notes: list[str] = []
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
    frame = ak.stock_zh_a_hist(
        symbol=normalize_stock_code(stock_code),
        period="daily",
        start_date=start,
        end_date=end,
        adjust="qfq",
    )
    notes.append(f"AKShare stock_zh_a_hist columns={list(frame.columns)}")
    rows = []
    for _, row in frame.iterrows():
        date_value = _pick(row, ["日期", "date", "交易日期"])
        if pd.isna(date_value):
            continue
        rows.append(
            {
                "stock_code": normalize_stock_code(stock_code),
                "trade_date": str(date_value).replace("-", "")[:8],
                "open": as_float(_pick(row, ["开盘", "open"])),
                "high": as_float(_pick(row, ["最高", "high"])),
                "low": as_float(_pick(row, ["最低", "low"])),
                "close": as_float(_pick(row, ["收盘", "close"])),
                "pre_close": None,
                "volume": as_float(_pick(row, ["成交量", "volume"])),
                "amount": as_float(_pick(row, ["成交额", "amount"])),
                "adj_factor": None,
                "source": "akshare.stock_zh_a_hist",
                "updated_at": now_text(),
            }
        )
    return rows, notes


def fetch_latest_quotes(stock_codes: list[str]) -> tuple[list[dict], list[str]]:
    ak = _import_akshare()
    wanted = {normalize_stock_code(code) for code in stock_codes if normalize_stock_code(code)}
    if not wanted:
        return [], []
    notes: list[str] = []
    try:
        frame = ak.stock_zh_a_spot_em()
        notes.append(f"AKShare stock_zh_a_spot_em columns={list(frame.columns)}")
        code_names = ["代码", "code"]
        name_names = ["名称", "name"]
        price_names = ["最新价", "最新", "price"]
        amount_names = ["成交额", "amount"]
    except Exception as exc:
        notes.append(f"stock_zh_a_spot_em failed, fallback to stock_zh_a_spot: {exc}")
        frame = ak.stock_zh_a_spot()
        notes.append(f"AKShare stock_zh_a_spot columns={list(frame.columns)}")
        code_names = ["代码", "code"]
        name_names = ["名称", "name"]
        price_names = ["最新价", "最新", "price"]
        amount_names = ["成交额", "amount"]
    today = datetime.now().strftime("%Y%m%d")
    rows = []
    for _, row in frame.iterrows():
        code = normalize_stock_code(_pick(row, code_names))
        if code not in wanted:
            continue
        price = as_float(_pick(row, price_names))
        if price is None or price <= 0:
            continue
        rows.append(
            {
                "stock_code": code,
                "trade_date": today,
                "open": None,
                "high": None,
                "low": None,
                "close": price,
                "pre_close": None,
                "volume": None,
                "amount": as_float(_pick(row, amount_names)),
                "adj_factor": None,
                "source": "akshare.latest_quote",
                "updated_at": now_text(),
            }
        )
    return rows, notes


def fetch_research_reports(days: int, rating_map: dict[str, str]) -> tuple[list[dict], list[dict], list[str]]:
    ak = _import_akshare()
    notes: list[str] = []
    report_rows: list[dict] = []
    rating_rows: list[dict] = []
    for offset in range(days):
        date_text = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            frame = ak.stock_rank_forecast_cninfo(date=date_text)
            if frame is None or frame.empty:
                continue
            notes.append(f"AKShare stock_rank_forecast_cninfo({date_text}) columns={list(frame.columns)}")
            reports, ratings = parse_cninfo_forecast_frame(frame, rating_map)
            report_rows.extend(reports)
            rating_rows.extend(ratings)
        except Exception as exc:
            notes.append(f"stock_rank_forecast_cninfo({date_text}) failed: {exc}")
            continue
    if report_rows or rating_rows:
        return report_rows, rating_rows, notes
    try:
        try:
            frame = ak.stock_research_report_em(symbol="全部")
        except TypeError:
            frame = ak.stock_research_report_em()
    except Exception as exc:
        notes.append(f"stock_research_report_em fallback failed: {exc}")
        return [], [], notes
    notes.append(f"AKShare stock_research_report_em columns={list(frame.columns)}")
    cutoff = datetime.now() - timedelta(days=days)
    for _, row in frame.iterrows():
        code = normalize_stock_code(_pick(row, ["股票代码", "代码", "stock_code"]))
        date_raw = _pick(row, ["日期", "发布时间", "publish_date"])
        publish_date = str(date_raw).replace("-", "")[:8] if date_raw is not None else ""
        try:
            if publish_date and datetime.strptime(publish_date, "%Y%m%d") < cutoff:
                continue
        except ValueError:
            pass
        title = str(_pick(row, ["报告名称", "报告标题", "title"]) or "")
        broker = str(_pick(row, ["机构", "券商", "broker"]) or "")
        rating = str(_pick(row, ["评级", "投资评级", "rating"]) or "")
        normalized = rating_map.get(rating, rating_map.get(rating.strip(), ""))
        target = as_float(_pick(row, ["目标价", "目标价格", "target_price"]))
        analyst = str(_pick(row, ["分析师", "analyst"]) or "")
        stock_name = str(_pick(row, ["股票简称", "名称", "stock_name"]) or "")
        url = str(_pick(row, ["报告链接", "pdf_url", "url"]) or "")
        report_id = stable_id(code, publish_date, broker, title)
        report_rows.append(
            {
                "id": report_id,
                "stock_code": code,
                "stock_name": stock_name,
                "report_title": title,
                "broker": broker,
                "rating": rating,
                "normalized_rating": normalized,
                "report_count_1m": None,
                "eps_y0": None,
                "eps_y1": None,
                "eps_y2": None,
                "pe_y0": None,
                "pe_y1": None,
                "pe_y2": None,
                "industry": None,
                "publish_date": publish_date,
                "pdf_url": url,
                "source": "akshare.stock_research_report_em",
                "created_at": now_text(),
                "updated_at": now_text(),
            }
        )
        rating_rows.append(
            {
                "id": stable_id("rating", report_id),
                "stock_code": code,
                "stock_name": stock_name,
                "publish_date": publish_date,
                "broker": broker,
                "analyst_raw": analyst,
                "rating": rating,
                "normalized_rating": normalized,
                "rating_change": None,
                "previous_rating": None,
                "target_price_low": None,
                "target_price_high": None,
                "target_price": target,
                "source": "akshare.stock_research_report_em",
                "source_url": url,
                "created_at": now_text(),
                "updated_at": now_text(),
            }
        )
    return report_rows, rating_rows, notes


def parse_cninfo_forecast_frame(
    frame: pd.DataFrame, rating_map: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    report_rows: list[dict] = []
    rating_rows: list[dict] = []
    for _, row in frame.iterrows():
        code = normalize_stock_code(_pick_by_names_or_pos(row, ["证券代码"], 0))
        stock_name = str(_pick_by_names_or_pos(row, ["证券简称"], 1) or "")
        publish_date = str(_pick_by_names_or_pos(row, ["发布日期", "报告日期"], 2) or "").replace("-", "")[:8]
        broker = str(_pick_by_names_or_pos(row, ["研究机构名称", "机构"], 3) or "")
        analyst = str(_pick_by_names_or_pos(row, ["研究员名称", "分析师"], 4) or "")
        rating = str(_pick_by_names_or_pos(row, ["投资评级", "评级"], 5) or "")
        rating_change = str(_pick_by_names_or_pos(row, ["评级变化"], 7) or "")
        previous_rating = str(_pick_by_names_or_pos(row, ["前一次投资评级"], 8) or "")
        low = as_float(_pick_by_names_or_pos(row, ["目标价格-下限"], 9))
        high = as_float(_pick_by_names_or_pos(row, ["目标价格-上限"], 10))
        if low is not None and high is not None:
            target = (low + high) / 2
        else:
            target = low if low is not None else high
        normalized = rating_map.get(rating, rating_map.get(rating.strip(), ""))
        report_id = stable_id("cninfo", code, publish_date, broker, analyst, target)
        report_rows.append(
            {
                "id": report_id,
                "stock_code": code,
                "stock_name": stock_name,
                "report_title": "巨潮投资评级",
                "broker": broker,
                "rating": rating,
                "normalized_rating": normalized,
                "report_count_1m": None,
                "eps_y0": None,
                "eps_y1": None,
                "eps_y2": None,
                "pe_y0": None,
                "pe_y1": None,
                "pe_y2": None,
                "industry": None,
                "publish_date": publish_date,
                "pdf_url": "",
                "source": "akshare.stock_rank_forecast_cninfo",
                "created_at": now_text(),
                "updated_at": now_text(),
            }
        )
        rating_rows.append(
            {
                "id": stable_id("rating", report_id),
                "stock_code": code,
                "stock_name": stock_name,
                "publish_date": publish_date,
                "broker": broker,
                "analyst_raw": analyst,
                "rating": rating,
                "normalized_rating": normalized,
                "rating_change": rating_change,
                "previous_rating": previous_rating,
                "target_price_low": low,
                "target_price_high": high,
                "target_price": target,
                "source": "akshare.stock_rank_forecast_cninfo",
                "source_url": "",
                "created_at": now_text(),
                "updated_at": now_text(),
            }
        )
    return report_rows, rating_rows
