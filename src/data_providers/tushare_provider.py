from __future__ import annotations

from datetime import datetime, timedelta

from src.utils.codes import normalize_stock_code, to_ts_code
from src.utils.normalize import as_float, now_text


class TushareProvider:
    def __init__(self, token: str):
        import tushare as ts

        ts.set_token(token)
        self.pro = ts.pro_api(token)

    def stock_universe(self) -> tuple[list[dict], list[str]]:
        frame = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,list_date,delist_date,list_status",
        )
        rows = []
        for _, row in frame.iterrows():
            code = normalize_stock_code(row.get("symbol"))
            name = str(row.get("name") or "")
            rows.append(
                {
                    "stock_code": code,
                    "ts_code": row.get("ts_code") or to_ts_code(code),
                    "stock_name": name,
                    "exchange": str(row.get("ts_code", "")).split(".")[-1],
                    "list_date": row.get("list_date"),
                    "delist_date": row.get("delist_date"),
                    "industry": row.get("industry"),
                    "list_status": row.get("list_status") or "L",
                    "is_st": 1 if "ST" in name.upper() else 0,
                    "updated_at": now_text(),
                }
            )
        return rows, [f"Tushare stock_basic columns={list(frame.columns)}"]

    def daily_bars(self, stock_code: str, days: int) -> tuple[list[dict], list[dict], list[str]]:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
        ts_code = to_ts_code(stock_code)
        daily = self.pro.daily(ts_code=ts_code, start_date=start, end_date=end)
        basic = self.pro.daily_basic(ts_code=ts_code, start_date=start, end_date=end)
        bar_rows = []
        for _, row in daily.iterrows():
            bar_rows.append(
                {
                    "stock_code": normalize_stock_code(row.get("ts_code")),
                    "trade_date": row.get("trade_date"),
                    "open": as_float(row.get("open")),
                    "high": as_float(row.get("high")),
                    "low": as_float(row.get("low")),
                    "close": as_float(row.get("close")),
                    "pre_close": as_float(row.get("pre_close")),
                    "volume": as_float(row.get("vol")),
                    "amount": as_float(row.get("amount")),
                    "adj_factor": None,
                    "source": "tushare.daily",
                    "updated_at": now_text(),
                }
            )
        basic_rows = []
        for _, row in basic.iterrows():
            basic_rows.append(
                {
                    "stock_code": normalize_stock_code(row.get("ts_code")),
                    "trade_date": row.get("trade_date"),
                    "close": as_float(row.get("close")),
                    "turnover_rate": as_float(row.get("turnover_rate")),
                    "volume_ratio": as_float(row.get("volume_ratio")),
                    "pe": as_float(row.get("pe")),
                    "pe_ttm": as_float(row.get("pe_ttm")),
                    "pb": as_float(row.get("pb")),
                    "ps": as_float(row.get("ps")),
                    "total_mv": as_float(row.get("total_mv")),
                    "circ_mv": as_float(row.get("circ_mv")),
                    "source": "tushare.daily_basic",
                    "updated_at": now_text(),
                }
            )
        return bar_rows, basic_rows, [
            f"Tushare daily columns={list(daily.columns)}",
            f"Tushare daily_basic columns={list(basic.columns)}",
        ]
