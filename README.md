# A股明星分析师预期上修共识策略系统

个人研究用低成本 MVP。第一版只提供 CLI、SQLite 数据库、AKShare 默认数据源、可选 Tushare 补充数据源，不自动下单。

## 快速开始

1. 安装依赖：

```powershell
python -m pip install -r requirements.txt
```

2. 如需 Tushare，将 `.env.example` 复制为 `.env` 并填写：

```env
TUSHARE_TOKEN=
USE_TUSHARE=false
USE_AKSHARE=true
DB_URL=sqlite:///data/strategy.db
```

3. 初始化和运行：

```powershell
python -m src.cli init-db
python -m src.cli import-analysts
python -m src.cli fetch-hibor-analysts
python -m src.cli update-stock-universe
python -m src.cli update-market --days 180
python -m src.cli update-reports --days 30
python -m src.cli weekly-run
```

输出目录：`outputs/weekly/<run_date>/`。

每次周报会生成：

- `weekly_report.md`：可读版周报。
- `candidates_top20.csv`：Top20 候选池。
- `portfolio_suggestion.csv`：8 只建议组合；如果严格过滤无人通过，会标记为研究观察组合。
- `weekly_report.xlsx`：候选池、建议组合、数据质量三张表。

## 当前版本范围

- 已实现 Phase 0：项目骨架、YAML 配置、SQLite 初始化、CLI。
- 已实现 Phase 1 基础版：股票基础信息、日行情、研报/评级、手工明星分析师名单导入。
- 支持从慧博知名分析师榜单抓取并去重导入明星分析师：
  `python -m src.cli fetch-hibor-analysts`
- 已实现 Phase 2 基础版：过滤、明星分析师匹配、目标价空间、目标价上修、研报后价格反应、趋势分、综合打分和建议组合选择。
- Tushare Token 为空时会自动关闭 Tushare，使用 AKShare。
- 外部接口失败时记录到 `data_quality_report` 和 `logs/strategy.log`，流程继续运行。
- 研报只保存链接或来源，不自动下载 PDF。

## Phase 2 策略说明

核心策略逻辑位于 `src/strategy/`，并由单元测试覆盖：

- `filters.py`：硬过滤与软警告，返回可解释原因。
- `factors.py`：目标价空间、目标价上修、盈利预测上修、研报后价格反应、趋势分。
- `scorer.py`：按 `config/strategy.yaml` 权重计算综合分。
- `portfolio.py`：按分数和行业上限生成建议组合。

## 注意

`config/strategy.yaml` 里的 `max_market_update_stocks` 控制行情更新的股票数量上限，第一版默认限制较小，避免个人环境第一次运行过慢。

## 可选 Streamlit 面板

安装依赖后可运行：

```powershell
streamlit run src/dashboard/app.py
```

面板只读取本地 SQLite 和最近一次周报数据，不会自动下单。
