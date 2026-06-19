from __future__ import annotations


def normalize_stock_code(value: object) -> str:
    raw = str(value or "").strip()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def to_ts_code(stock_code: str) -> str:
    code = normalize_stock_code(stock_code)
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"
