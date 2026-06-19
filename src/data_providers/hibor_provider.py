from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup


BIGTYPE_AWARD = {
    1: "证券业金牛分析师评选",
    2: "新财富最佳分析师评选",
    3: "证券业水晶球分析师评选",
}


DEFAULT_HIBOR_URLS = [
    "https://www.hibor.com.cn/author.html?year=2025&bigtype=2",
    "https://www.hibor.com.cn/author.html?year=2024&bigtype=2",
    "https://www.hibor.com.cn/author.html?year=2023&bigtype=2",
    "https://www.hibor.com.cn/author.html?year=2024&bigtype=1",
    "https://www.hibor.com.cn/author.html?year=2022&bigtype=1",
    "https://www.hibor.com.cn/author.html?year=2024&bigtype=3",
    "https://www.hibor.com.cn/author.html?year=2023&bigtype=3",
]


def infer_year_bigtype(url: str) -> tuple[int | None, int | None]:
    query = parse_qs(urlparse(url).query)
    year = int(query["year"][0]) if query.get("year") else None
    bigtype = int(query["bigtype"][0]) if query.get("bigtype") else None
    return year, bigtype


def fetch_hibor_author_html(url: str, timeout: int = 30) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.hibor.com.cn/author.html",
        },
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def _clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = value.replace("\u3000", " ")
    return value.strip()


def _clean_industry(value: str) -> str:
    value = _clean_text(value)
    value = re.sub(r"^（[^）]+）", "", value)
    value = re.sub(r"^\([^)]*\)", "", value)
    return value.strip()


def _split_analysts(value: str) -> list[str]:
    value = _clean_text(value)
    parts = re.split(r"[，,、/；;]+|\s+，\s+|\s+、\s+", value)
    return [_clean_text(part) for part in parts if _clean_text(part)]


def _author_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        cells = [cell.get_text(" ", strip=True) for cell in first_row.find_all(["td", "th"])]
        joined = "|".join(cells)
        if "研究领域" in joined and "所属机构" in joined and "分析师" in joined:
            return table
    return None


def parse_hibor_author_html(
    html: str,
    source_url: str,
    year: int | None = None,
    bigtype: int | None = None,
) -> list[dict]:
    if year is None or bigtype is None:
        inferred_year, inferred_bigtype = infer_year_bigtype(source_url)
        year = year or inferred_year
        bigtype = bigtype or inferred_bigtype
    soup = BeautifulSoup(html, "html.parser")
    table = _author_table(soup)
    if table is None:
        return []

    rows: list[dict] = []
    seen: set[tuple] = set()
    current_industry = ""
    for tr in table.find_all("tr")[1:]:
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        industry, rank, broker, analysts_raw = cells[:4]
        if industry:
            current_industry = _clean_industry(industry)
        industry = current_industry
        broker = _clean_text(broker)
        rank = _clean_text(rank)
        if not industry or not broker or not analysts_raw:
            continue
        for analyst in _split_analysts(analysts_raw):
            key = (analyst, broker, industry, year, bigtype, rank)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "analyst_name": analyst,
                    "broker": broker,
                    "team_name": f"{analyst}团队",
                    "industry": industry,
                    "award_name": BIGTYPE_AWARD.get(bigtype or 0, f"慧博榜单{bigtype}"),
                    "award_year": year,
                    "rank": rank,
                    "source_note": f"慧博知名分析师榜单 {source_url}",
                    "active": 1,
                }
            )
    return rows


def fetch_hibor_analysts(urls: list[str] | None = None) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    notes: list[str] = []
    for url in urls or DEFAULT_HIBOR_URLS:
        year, bigtype = infer_year_bigtype(url)
        try:
            html = fetch_hibor_author_html(url)
            parsed = parse_hibor_author_html(html, url, year=year, bigtype=bigtype)
            rows.extend(parsed)
            notes.append(f"{url} parsed_rows={len(parsed)}")
        except Exception as exc:
            notes.append(f"{url} failed: {exc}")
    return rows, notes
