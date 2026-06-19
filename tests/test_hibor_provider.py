from pathlib import Path

from src import db
from src.data_providers.hibor_provider import parse_hibor_author_html
from src.pipeline.import_hibor_analysts import import_hibor_analysts


HTML = """
<html><body>
<table></table><table></table>
<table>
  <tr><th>研究领域</th><th>名次</th><th>所属机构</th><th>分析师</th></tr>
  <tr><td>（C）策略研究</td><td>1</td><td>广发证券</td><td>刘晨明 ， 郑恺</td></tr>
  <tr><td></td><td>1</td><td>广发证券</td><td>刘晨明 ， 郑恺</td></tr>
  <tr><td></td><td>2</td><td>申万宏源</td><td>傅静涛</td></tr>
</table>
</body></html>
"""


def test_parse_hibor_author_html_splits_analysts_and_dedupes_rows():
    rows = parse_hibor_author_html(
        HTML,
        source_url="https://example.test/author.html?year=2025&bigtype=2",
        year=2025,
        bigtype=2,
    )

    assert len(rows) == 3
    assert rows[0]["analyst_name"] == "刘晨明"
    assert rows[0]["broker"] == "广发证券"
    assert rows[0]["industry"] == "策略研究"
    assert rows[0]["award_name"] == "新财富最佳分析师评选"
    assert rows[0]["award_year"] == 2025
    assert rows[0]["rank"] == "1"
    assert rows[1]["analyst_name"] == "郑恺"
    assert rows[2]["analyst_name"] == "傅静涛"


def test_import_hibor_analysts_upserts_without_duplicate_growth(tmp_path):
    db_path = tmp_path / "strategy.db"
    db.init_db(db_path)

    rows = parse_hibor_author_html(
        HTML,
        source_url="https://example.test/author.html?year=2025&bigtype=2",
        year=2025,
        bigtype=2,
    )
    first = import_hibor_analysts(db_path, rows)
    second = import_hibor_analysts(db_path, rows)

    assert first == 3
    assert second == 3
    with db.connect(db_path) as conn:
        count = conn.execute("select count(*) from analyst_awards").fetchone()[0]
    assert count == 3
