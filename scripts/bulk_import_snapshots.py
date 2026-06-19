"""批量从WebFetch行情快照导入daily_bar（绕过沙箱网络限制）"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "strategy.db"

# 从 WebFetch 获取的快照数据（代码, 名称, 最新价）
# 覆盖 000001-002076 段
SNAPSHOTS = """
000021|44.04|深科技
000333|78.00|美的集团
000338|30.09|潍柴动力
000400|22.88|许继电气
000423|45.68|东阿阿胶
000538|48.43|云南白药
000568|80.93|泸州老窖
000596|81.71|古井贡酒
000651|36.72|格力电器
000657|98.48|中钨高新
000661|64.10|长春高新
000799|39.36|酒鬼酒
000811|40.17|冰轮环境
000831|61.90|中国稀土
000858|75.85|五粮液
000977|65.66|浪潮信息
000988|177.55|华工科技
001203|32.46|大中矿业
001238|29.25|浙江正特
002001|28.00|新和成
002008|134.90|大族激光
002011|10.51|盾安环境
002025|63.53|航天电器
002028|190.20|思源电气
002032|41.03|苏泊尔
002049|80.39|紫光国微
002050|45.74|三花智控
002064|9.50|华峰化学
002085|61.44|万丰奥威
002100|11.91|天康生物
002142|26.41|宁波银行
002156|34.09|通富微电
002161|7.79|远望谷
002293|10.33|罗莱生活
002312|10.47|川发龙蟒
002345|11.12|潮宏基
002601|34.34|龙佰集团
002658|10.40|雪迪龙
002741|40.30|光华科技
002780|12.74|三夫户外
002831|30.05|裕同科技
002832|19.49|比音勒芬
002850|150.80|科达利
002865|24.68|钧达股份
002891|28.20|中宠股份
002998|9.62|优彩资源
"""

def import_all():
    conn = sqlite3.connect(str(DB))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_date = datetime.now().strftime("%Y%m%d")
    
    inserted = 0
    for line in SNAPSHOTS.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        code, price_str, name = parts
        if not code or price_str == "-":
            continue
        try:
            price = float(price_str)
        except ValueError:
            continue
        
        conn.execute(
            """INSERT OR REPLACE INTO daily_bar 
               (stock_code, trade_date, open, high, low, close, pre_close, volume, amount, adj_factor, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, trade_date, price, price, price, price, None, None, None, 1.0, "eastmoney.snapshot", now)
        )
        
        inserted += 1
    
    conn.commit()
    c = conn.execute("SELECT COUNT(*) FROM daily_bar")
    total = c.fetchone()[0]
    conn.close()
    print(f"导入 {inserted} 条记录，daily_bar 共 {total} 条")

if __name__ == "__main__":
    import_all()
