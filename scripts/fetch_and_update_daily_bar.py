"""
用 WebFetch 获取行情快照，填充 daily_bar 表。
因为沙箱环境限制 Python 直连东方财富，改为用 WebFetch 预拉取数据后导入。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 行情快照 JSON 文件存储目录
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "strategy.db"


def import_snapshot_to_db(json_path: Path, db_path: Path):
    import sqlite3
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    diff = data.get("data", {}).get("diff", [])
    if not diff:
        print(f"空数据: {json_path}")
        return 0
    
    conn = sqlite3.connect(str(db_path))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_date = datetime.now().strftime("%Y%m%d")
    
    inserted = 0
    for item in diff:
        code = str(item.get("f12", ""))
        price_str = item.get("f2", "")
        if not code or price_str == "-":
            continue
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            continue
        
        # 确定 secid
        if code.startswith("6") or code.startswith("9"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"
        
        conn.execute(
            """INSERT OR REPLACE INTO daily_bar 
               (stock_code, trade_date, open, high, low, close, pre_close, volume, amount, adj_factor, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, trade_date, price, price, price, price, None, None, None, 1.0, "eastmoney.snapshot", now)
        )
        inserted += 1
    
    conn.commit()
    conn.close()
    print(f"从 {json_path.name} 导入了 {inserted} 条记录")
    return inserted


if __name__ == "__main__":
    if not SNAPSHOT_DIR.exists():
        print(f"快照目录不存在: {SNAPSHOT_DIR}")
        print("请先用 WebFetch 拉取行情快照保存到此目录")
        sys.exit(1)
    
    total = 0
    for f in sorted(SNAPSHOT_DIR.glob("snapshot_*.json")):
        total += import_snapshot_to_db(f, DB_PATH)
    
    print(f"总计导入 {total} 条记录")
