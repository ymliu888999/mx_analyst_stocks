# Streamlit Community Cloud 部署说明

## 你需要做什么

1. 准备一个 GitHub 账号。
2. 新建一个 GitHub 仓库，把本项目上传到仓库。
3. 打开 Streamlit Community Cloud，使用 GitHub 登录。
4. 点击 `Create app`，选择这个仓库。
5. Main file path 填：`src/dashboard/app.py`。
6. Advanced settings / Secrets 中填入下面内容。

```toml
TUSHARE_TOKEN = ""
USE_TUSHARE = "false"
USE_AKSHARE = "true"
DB_URL = "sqlite:///data/strategy.db"
TIMEZONE = "Asia/Shanghai"
DEFAULT_MARKET_INDEX = "000300.SH"
```

如果你有 Tushare Token，把 `TUSHARE_TOKEN` 填进去，并把 `USE_TUSHARE` 改成 `true`。

## 费用

Streamlit Community Cloud 当前官方说明是 Community Cloud 可免费部署公开应用。适合个人研究 MVP。

## 重要限制

- 免费 Community Cloud 更适合公开项目；如果仓库或 App 需要私密访问，请以 Streamlit 当时页面提示为准。
- SQLite 文件在云端运行时不适合作为长期可写数据库。页面上的新增、修改、删除可能在应用重启后丢失。
- 第一版建议把它当作展示和手动刷新面板；长期在线保存数据，后续再迁移到云数据库。
- AKShare/Tushare 外部接口偶发失败属于正常情况，程序会记录质量报告并继续运行。
