from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.pipeline.weekly_run import run_weekly
from src.settings import load_settings
from src.utils.normalize import now_text, stable_id


ANALYST_FIELDS = [
    "analyst_name",
    "broker",
    "team_name",
    "industry",
    "award_name",
    "award_year",
    "rank",
    "source_note",
    "active",
]


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _read_frame(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def load_analysts(db_path: Path | str | None = None, include_inactive: bool = False) -> pd.DataFrame:
    db_path = db_path or load_settings().db_path
    where = "" if include_inactive else "where active=1"
    with _connect(db_path) as conn:
        return _read_frame(
            conn,
            f"""select id, analyst_name, broker, team_name, industry, award_name,
            award_year, rank, source_note, active, updated_at
            from analyst_awards {where}
            order by active desc, industry, broker, analyst_name""",
        )


def create_analyst(db_path: Path | str, data: dict[str, Any]) -> str:
    row = {field: data.get(field) for field in ANALYST_FIELDS}
    row["active"] = int(row.get("active") if row.get("active") is not None else 1)
    row["award_year"] = int(row["award_year"]) if row.get("award_year") not in (None, "") else None
    row["id"] = stable_id(
        row.get("analyst_name"),
        row.get("broker"),
        row.get("team_name"),
        row.get("industry"),
        now_text(),
    )
    row["created_at"] = now_text()
    row["updated_at"] = now_text()
    keys = list(row.keys())
    with _connect(db_path) as conn:
        conn.execute(
            f"insert into analyst_awards ({','.join(keys)}) values ({','.join('?' for _ in keys)})",
            [row[key] for key in keys],
        )
        conn.commit()
    return row["id"]


def update_analyst(db_path: Path | str, analyst_id: str, changes: dict[str, Any]) -> None:
    allowed = {key: value for key, value in changes.items() if key in ANALYST_FIELDS}
    if not allowed:
        return
    if "active" in allowed:
        allowed["active"] = int(allowed["active"])
    if "award_year" in allowed and allowed["award_year"] not in (None, ""):
        allowed["award_year"] = int(allowed["award_year"])
    allowed["updated_at"] = now_text()
    assignments = ",".join(f"{key}=?" for key in allowed)
    with _connect(db_path) as conn:
        conn.execute(
            f"update analyst_awards set {assignments} where id=?",
            [*allowed.values(), analyst_id],
        )
        conn.commit()


def delete_analyst(db_path: Path | str, analyst_id: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("delete from analyst_awards where id=?", (analyst_id,))
        conn.commit()


def latest_run_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("select max(run_date) from weekly_candidate").fetchone()
    return row[0] if row else None


def load_latest_weekly_tables(db_path: Path | str | None = None) -> dict[str, Any]:
    db_path = db_path or load_settings().db_path
    with _connect(db_path) as conn:
        run_date = latest_run_date(conn)
        if not run_date:
            return {
                "run_date": None,
                "candidates": pd.DataFrame(),
                "portfolio": pd.DataFrame(),
                "quality": pd.DataFrame(),
            }
        return {
            "run_date": run_date,
            "candidates": _read_frame(
                conn,
                "select * from weekly_candidate where run_date=? order by rank",
                (run_date,),
            ),
            "portfolio": _read_frame(
                conn,
                "select * from portfolio_suggestion where run_date=? order by rank",
                (run_date,),
            ),
            "quality": _read_frame(
                conn,
                "select * from data_quality_report where run_date=? order by severity, item",
                (run_date,),
            ),
        }


def get_dashboard_metrics(db_path: Path | str | None = None) -> dict[str, Any]:
    db_path = db_path or load_settings().db_path
    with _connect(db_path) as conn:
        run_time = conn.execute("select max(created_at) from weekly_candidate").fetchone()[0]
        analyst_count = conn.execute(
            """select count(*) from (
                select distinct analyst_name
                from analyst_awards
                where active=1 and analyst_name is not null
            )"""
        ).fetchone()[0]
    return {
        "latest_run_time": run_time,
        "distinct_analyst_count": analyst_count,
    }


def load_report_stock_details(db_path: Path | str | None = None) -> pd.DataFrame:
    db_path = db_path or load_settings().db_path
    with _connect(db_path) as conn:
        run_date = latest_run_date(conn)
        return _read_frame(
            conn,
            """with latest_price as (
                select d.stock_code, d.trade_date latest_trade_date, d.close latest_close, d.source quote_source
                from daily_bar d
                join (
                    select stock_code, max(trade_date) trade_date
                    from daily_bar group by stock_code
                ) x on x.stock_code=d.stock_code and x.trade_date=d.trade_date
            )
            select
                r.publish_date,
                r.stock_code,
                coalesce(r.stock_name, s.stock_name) stock_name,
                coalesce(s.industry, rr.industry) industry,
                r.broker,
                r.analyst_raw,
                r.rating,
                r.normalized_rating,
                r.target_price,
                p.latest_close,
                p.latest_trade_date,
                p.quote_source,
                case
                    when p.latest_close is not null and p.latest_close != 0 and r.target_price is not null
                    then r.target_price / p.latest_close - 1
                    else null
                end target_upside,
                c.effective_star_analyst_count,
                c.effective_broker_count,
                c.upside_score,
                c.consensus_score,
                c.target_revision_score,
                c.earnings_revision_score,
                c.price_reaction_score,
                c.trend_score,
                c.total_score,
                c.pass_filter,
                c.fail_reason,
                rr.pdf_url,
                r.source
            from research_rating r
            left join stock_master s on s.stock_code=r.stock_code
            left join research_report rr on rr.stock_code=r.stock_code and rr.publish_date=r.publish_date
            left join latest_price p on p.stock_code=r.stock_code
            left join weekly_candidate c on c.stock_code=r.stock_code and c.run_date=?
            order by r.publish_date desc, c.total_score desc, r.stock_code""",
            (run_date,),
        )


def load_selected_portfolio(db_path: Path | str | None = None) -> pd.DataFrame:
    db_path = db_path or load_settings().db_path
    with _connect(db_path) as conn:
        run_date = latest_run_date(conn)
        if not run_date:
            return pd.DataFrame()
        return _read_frame(
            conn,
            """select p.*, c.upside_score, c.consensus_score, c.target_revision_score,
            c.earnings_revision_score, c.price_reaction_score, c.trend_score,
            c.risk_penalty, c.fail_reason
            from portfolio_suggestion p
            left join weekly_candidate c on c.run_date=p.run_date and c.stock_code=p.stock_code
            where p.run_date=?
            order by p.rank""",
            (run_date,),
        )


def load_report_quality_summary(db_path: Path | str | None = None) -> pd.DataFrame:
    db_path = db_path or load_settings().db_path
    with _connect(db_path) as conn:
        rows = [
            {
                "item": "研报评级记录",
                "value": conn.execute("select count(*) from research_rating").fetchone()[0],
                "note": "当前本地库中的评级/研报信号条数",
            },
            {
                "item": "覆盖股票数",
                "value": conn.execute("select count(distinct stock_code) from research_rating").fetchone()[0],
                "note": "有评级记录的股票数量",
            },
            {
                "item": "有目标价记录",
                "value": conn.execute("select count(*) from research_rating where target_price is not null").fetchone()[0],
                "note": "目标价是计算空间的关键字段",
            },
            {
                "item": "目标价覆盖率",
                "value": conn.execute(
                    """select printf('%.1f%%',
                    100.0 * sum(case when target_price is not null then 1 else 0 end) / nullif(count(*), 0))
                    from research_rating"""
                ).fetchone()[0],
                "note": "覆盖率低会导致大量 target_upside_missing",
            },
            {
                "item": "最近研报日期",
                "value": conn.execute("select max(publish_date) from research_rating").fetchone()[0],
                "note": "用于判断数据是否新鲜",
            },
        ]
        by_source = _read_frame(
            conn,
            """select source item, count(*) value, '来源分布' note
            from research_rating group by source order by value desc""",
        )
    return pd.concat([pd.DataFrame(rows), by_source], ignore_index=True)


def load_process_summary(db_path: Path | str | None = None) -> pd.DataFrame:
    db_path = db_path or load_settings().db_path
    with _connect(db_path) as conn:
        run_date = latest_run_date(conn)
        items = []
        for table in [
            "stock_master",
            "daily_bar",
            "research_rating",
            "analyst_awards",
            "weekly_candidate",
            "portfolio_suggestion",
            "data_quality_report",
        ]:
            items.append(
                {
                    "step": table,
                    "rows": conn.execute(f"select count(*) from {table}").fetchone()[0],
                    "latest_run_date": run_date,
                }
            )
    return pd.DataFrame(items)


def _format_percent_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for column in ["target_upside", "weight", "upside_score", "consensus_score", "total_score"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


COLUMN_LABELS = {
    "run_date": "运行日期",
    "stock_code": "股票代码",
    "stock_name": "股票名称",
    "industry": "行业",
    "publish_date": "发布日期",
    "broker": "券商",
    "analyst_raw": "分析师",
    "rating": "评级",
    "normalized_rating": "标准评级",
    "target_price": "目标价",
    "latest_close": "现价",
    "latest_trade_date": "行情日期",
    "quote_source": "行情来源",
    "target_upside": "空间",
    "effective_star_analyst_count": "明星分析师数",
    "effective_broker_count": "券商数",
    "upside_score": "空间分",
    "consensus_score": "共识分",
    "target_revision_score": "目标价上修分",
    "earnings_revision_score": "盈利上修分",
    "price_reaction_score": "价格反应分",
    "trend_score": "趋势分",
    "risk_penalty": "风险扣分",
    "total_score": "总分",
    "rank": "排名",
    "pass_filter": "是否通过",
    "fail_reason": "入选/剔除原因",
    "pdf_url": "研报链接",
    "source": "数据来源",
    "weight": "权重",
    "reason": "原因",
    "analyst_name": "分析师",
    "team_name": "团队",
    "award_name": "奖项",
    "award_year": "年份",
    "source_note": "来源备注",
    "active": "启用",
    "updated_at": "更新时间",
    "item": "项目",
    "value": "数值",
    "note": "说明",
    "step": "步骤",
    "rows": "行数",
    "latest_run_date": "最新运行日期",
}


PERCENT_COLUMNS = {"空间", "权重", "空间分", "共识分", "总分", "目标价上修分", "盈利上修分", "价格反应分", "趋势分", "风险扣分"}


def _xueqiu_url(stock_code: str) -> str:
    code = str(stock_code or "").zfill(6)
    prefix = "SH" if code.startswith(("6", "9")) else "SZ"
    return f"https://xueqiu.com/S/{prefix}{code}"


def _display_frame(frame: pd.DataFrame, link_stock_code: bool = True) -> pd.DataFrame:
    frame = frame.copy()
    frame = frame.drop(columns=[col for col in frame.columns if col == "id"], errors="ignore")
    if link_stock_code and "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(
            lambda code: f"[{str(code).zfill(6)}]({_xueqiu_url(str(code).zfill(6))})"
        )
    frame = frame.rename(columns={key: value for key, value in COLUMN_LABELS.items() if key in frame.columns})
    for column in PERCENT_COLUMNS & set(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if column == "权重":
            frame[column] = frame[column].map(lambda x: f"{x:.1%}" if pd.notna(x) else "")
    return frame


def _render_table(frame: pd.DataFrame, *, link_stock_code: bool = True) -> None:
    import streamlit as st

    display = _display_frame(frame, link_stock_code=link_stock_code)
    column_config = {}
    if link_stock_code and "股票代码" in display.columns:
        column_config["股票代码"] = st.column_config.LinkColumn("股票代码", display_text=r"(\d{6})")
    st.dataframe(display, use_container_width=True, hide_index=True, column_config=column_config)


def _inject_style() -> None:
    import streamlit as st

    st.markdown(
        """
        <style>
        #MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] {
            display: none !important;
        }
        .block-container {
            padding-top: 0.25rem !important;
            padding-left: 1.4rem !important;
            padding-right: 1.4rem !important;
            max-width: 100%;
        }
        .stApp {
            background: linear-gradient(180deg, #fff7f0 0%, #f7fafc 38%, #ffffff 100%);
            color: #172033;
        }
        h1, h2, h3 {
            color: #8f1f25 !important;
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(143, 31, 37, 0.16);
            border-radius: 8px;
            padding: 0.7rem 0.9rem;
            box-shadow: 0 1px 8px rgba(23, 32, 51, 0.05);
        }
        [data-testid="stMetricLabel"] {
            font-size: 1.02rem !important;
            font-weight: 800 !important;
            color: #111827 !important;
            justify-content: center !important;
            text-align: center !important;
            width: 100%;
        }
        [data-testid="stMetricValue"] {
            font-size: 0.92rem !important;
            font-weight: 400 !important;
            color: #b91c1c !important;
            white-space: normal !important;
            line-height: 1.25 !important;
            text-align: center !important;
            width: 100%;
        }
        div.stButton > button {
            font-weight: 800 !important;
        }
        div[data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-primary"]) {
            width: 100% !important;
            display: flex;
            justify-content: flex-end;
        }
        div[data-testid="stButton"]:has(button[data-testid="stBaseButton-primary"]) {
            display: flex;
            justify-content: flex-end;
            width: 100%;
        }
        div[data-testid="stButton"]:has(button[data-testid="stBaseButton-primary"]) button {
            display: block;
            margin-left: auto;
            margin-right: 0;
            width: 112px;
        }
        .product-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0;
        }
        .logo-mark {
            width: 40px;
            height: 40px;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-weight: 800;
            background: linear-gradient(135deg, #9b1c23, #d6a23a);
            box-shadow: 0 3px 10px rgba(155, 28, 35, 0.22);
        }
        .product-title {
            font-size: clamp(1.35rem, 3vw, 2.25rem);
            line-height: 1.15;
            font-weight: 760;
            color: #8f1f25;
            margin: 0;
        }
        .signature {
            font-style: italic;
            color: #a07a2f;
            font-size: 0.95rem;
            white-space: nowrap;
        }
        @media (max-width: 720px) {
            .block-container {
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
            }
            .product-header {
                align-items: flex-start;
                flex-wrap: wrap;
            }
            .signature {
                width: 100%;
                margin-left: 48px;
            }
            div[data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-primary"]),
            div[data-testid="stButton"]:has(button[data-testid="stBaseButton-primary"]) {
                justify-content: flex-end;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header(db_path: Path, output_dir: Path) -> None:
    import streamlit as st

    title_col, refresh_col = st.columns([0.84, 0.16], vertical_alignment="center")
    with title_col:
        st.markdown(
            """
            <div class="product-header">
                <div class="logo-mark">策</div>
                <div class="product-title">明星分析师共识策略</div>
                <div class="signature">Sherman制作</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with refresh_col:
        if st.button("人工刷新", use_container_width=False, type="primary"):
            with st.spinner("正在重新计算周报..."):
                result = run_weekly(db_path, output_dir=output_dir)
            st.success(f"刷新完成：候选 {result['candidate_count']}，组合 {result['portfolio_count']}")
            st.rerun()


def _analyst_management(db_path: Path) -> None:
    import streamlit as st

    st.subheader("明星分析师维护")
    st.caption("这里直接维护 SQLite 中的 analyst_awards 表。删除为真实删除；如需保留历史，可把 active 改为 0。")

    with st.expander("新增明星分析师", expanded=False):
        with st.form("create_analyst_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            analyst_name = c1.text_input("分析师")
            broker = c2.text_input("券商")
            team_name = c3.text_input("团队")
            c4, c5, c6 = st.columns(3)
            industry = c4.text_input("行业")
            award_name = c5.text_input("奖项")
            award_year = c6.number_input("年份", min_value=2000, max_value=2100, value=2024)
            c7, c8 = st.columns(2)
            rank = c7.text_input("名次")
            source_note = c8.text_input("来源备注")
            submitted = st.form_submit_button("新增")
            if submitted:
                if not analyst_name or not broker:
                    st.error("分析师和券商必填")
                else:
                    create_analyst(
                        db_path,
                        {
                            "analyst_name": analyst_name,
                            "broker": broker,
                            "team_name": team_name,
                            "industry": industry,
                            "award_name": award_name,
                            "award_year": award_year,
                            "rank": rank,
                            "source_note": source_note,
                            "active": 1,
                        },
                    )
                    st.success("已新增")
                    st.rerun()

    analysts = load_analysts(db_path, include_inactive=True)
    _render_table(analysts, link_stock_code=False)
    if analysts.empty:
        return

    ids = analysts["id"].tolist()
    selected_id = st.selectbox(
        "选择要修改或删除的记录",
        ids,
        format_func=lambda value: analysts.loc[analysts["id"] == value, "analyst_name"].iloc[0],
    )
    row = analysts.loc[analysts["id"] == selected_id].iloc[0].to_dict()
    with st.form("edit_analyst_form"):
        c1, c2, c3 = st.columns(3)
        analyst_name = c1.text_input("分析师", value=str(row.get("analyst_name") or ""))
        broker = c2.text_input("券商", value=str(row.get("broker") or ""))
        team_name = c3.text_input("团队", value=str(row.get("team_name") or ""))
        c4, c5, c6 = st.columns(3)
        industry = c4.text_input("行业", value=str(row.get("industry") or ""))
        award_name = c5.text_input("奖项", value=str(row.get("award_name") or ""))
        award_year = c6.number_input(
            "年份",
            min_value=2000,
            max_value=2100,
            value=int(row.get("award_year") or 2024),
        )
        c7, c8, c9 = st.columns(3)
        rank = c7.text_input("名次", value=str(row.get("rank") or ""))
        source_note = c8.text_input("来源备注", value=str(row.get("source_note") or ""))
        active = c9.checkbox("启用", value=bool(row.get("active")))
        save, delete = st.columns(2)
        save_clicked = save.form_submit_button("保存修改")
        delete_clicked = delete.form_submit_button("删除")
        if save_clicked:
            update_analyst(
                db_path,
                selected_id,
                {
                    "analyst_name": analyst_name,
                    "broker": broker,
                    "team_name": team_name,
                    "industry": industry,
                    "award_name": award_name,
                    "award_year": award_year,
                    "rank": rank,
                    "source_note": source_note,
                    "active": int(active),
                },
            )
            st.success("已保存")
            st.rerun()
        if delete_clicked:
            delete_analyst(db_path, selected_id)
            st.success("已删除")
            st.rerun()


def main() -> None:
    import streamlit as st

    settings = load_settings()
    db_path = settings.db_path
    output_dir = settings.root / "outputs"
    st.set_page_config(page_title="明星分析师共识策略", layout="wide")
    _inject_style()
    _render_header(db_path, output_dir)

    tables = load_latest_weekly_tables(db_path)
    run_date = tables["run_date"]
    metrics = get_dashboard_metrics(db_path)
    candidates = tables["candidates"]
    portfolio = load_selected_portfolio(db_path)
    quality = tables["quality"]
    report_details = load_report_stock_details(db_path)
    report_quality = load_report_quality_summary(db_path)
    process = load_process_summary(db_path)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("最新运行时间", metrics["latest_run_time"] or run_date or "-")
    c2.metric("分析师人数", metrics["distinct_analyst_count"])
    c3.metric("覆盖股票数", report_details["stock_code"].nunique() if "stock_code" in report_details.columns else 0)
    c4.metric("股票候选池", len(candidates))
    c5.metric("终选股票数", len(portfolio))

    tab_portfolio, tab_analysts, tab_reports, tab_candidates, tab_quality, tab_overview = st.tabs(
        ["最终组合", "明星分析师", "研报股票明细", "候选池与得分", "数据质量", "流程总览"]
    )

    with tab_portfolio:
        st.subheader("最终选中股票名单")
        st.caption("weight 按 8 只组合等权展示，单只为 12.5%；未使用仓位留待人工确认。")
        _render_table(portfolio)

    with tab_analysts:
        _analyst_management(db_path)

    with tab_reports:
        st.subheader("明星分析师研报中的股票详情")
        st.caption("包含分析师、行业、股票、目标价、现价、空间、得分和剔除原因。")
        _render_table(report_details)

    with tab_candidates:
        st.subheader("候选池与得分拆解")
        st.caption("每一列都可排序；fail_reason 显示入选或剔除原因。")
        _render_table(candidates)

    with tab_quality:
        st.subheader("研报数量与关键字段覆盖")
        _render_table(report_quality, link_stock_code=False)
        st.subheader("数据质量和接口状态")
        st.caption("外部接口失败、字段映射和缺失数据会记录在这里。")
        _render_table(quality, link_stock_code=False)

    with tab_overview:
        st.subheader("每一步产物")
        _render_table(process, link_stock_code=False)
        st.subheader("筛选与打分逻辑")
        st.markdown(
            """
            **数据准备**

            - 股票基础表来自 AKShare 或 Tushare，记录股票代码、名称、行业、ST 状态。
            - 行情表记录日线收盘价、成交额，用于计算现价、20 日/60 日涨幅、均线和流动性。
            - 研报/评级表记录券商、分析师、评级、目标价和发布日期。
            - 明星分析师库来自手工 CSV 和慧博榜单，匹配时优先使用“分析师姓名 + 券商”。

            **硬过滤**

            - 目标价空间必须不低于配置中的最低空间。
            - 至少需要 2 家券商形成共识。
            - 至少需要 2 位匹配成功的明星分析师。
            - ST、重大风险、流动性不足、研报后涨幅过大等会被剔除。

            **软提示**

            - 研报后价格反应过弱、价格低于 MA60、中等风险事件、只匹配到分析师姓名但券商不一致，会写入 warning。
            - warning 不一定剔除，但会帮助人工复核。

            **打分**

            - 目标价空间、明星共识、目标价上修、盈利预测上修、研报后价格反应、趋势分按 `config/strategy.yaml` 权重加权。
            - 缺历史数据时使用中性分，避免第一版因为缺字段完全崩掉。
            - `fail_reason` 会保留每只股票通过或剔除的直接原因。

            **组合**

            - 正式组合只从 `pass_filter=1` 的股票中选取，并受行业上限约束。
            - 仓位按 8 只组合等权展示，每只固定 12.5%。即使当前只选出 2 只，也显示为 12.5%，剩余仓位留空等待人工确认。
            - 如果没有严格通过股票，系统会给出 `research_fallback` 研究观察名单，但不会冒充正式通过。
            """
        )


if __name__ == "__main__":
    main()
