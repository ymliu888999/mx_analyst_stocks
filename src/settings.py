from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    root: Path
    db_path: Path
    use_akshare: bool
    use_tushare: bool
    tushare_token: str
    timezone: str
    strategy: dict[str, Any]
    rating_map: dict[str, str]
    broker_alias: dict[str, str]


def _load_streamlit_secrets() -> None:
    try:
        import streamlit as st
    except Exception:
        return
    try:
        secrets = dict(st.secrets)
    except Exception:
        return
    for key, value in secrets.items():
        if isinstance(value, (str, int, float, bool)) and os.getenv(key) is None:
            os.environ[key] = str(value)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _db_path_from_url(raw: str | None) -> Path:
    raw = raw or "sqlite:///data/strategy.db"
    if raw.startswith("sqlite:///"):
        return ROOT / raw.replace("sqlite:///", "", 1)
    return ROOT / raw


def load_yaml(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    _load_streamlit_secrets()
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    requested_tushare = _bool_env("USE_TUSHARE", False)
    return Settings(
        root=ROOT,
        db_path=_db_path_from_url(os.getenv("DB_URL")),
        use_akshare=_bool_env("USE_AKSHARE", True),
        use_tushare=bool(token) and requested_tushare,
        tushare_token=token,
        timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
        strategy=load_yaml(ROOT / "config" / "strategy.yaml"),
        rating_map=load_yaml(ROOT / "config" / "rating_map.yaml"),
        broker_alias=load_yaml(ROOT / "config" / "broker_alias.yaml"),
    )
