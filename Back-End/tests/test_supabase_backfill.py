from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from scripts.backfill_supabase_cache import (
    load_financial_records,
    load_news_records,
)


UTC = timezone.utc


def test_financial_backfill_filters_expired_rows(tmp_path):
    path = tmp_path / "financial.sqlite3"
    now = datetime(2026, 7, 19, tzinfo=UTC)
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE company_metadata (
                ticker TEXT, payload TEXT, fetched_at TEXT, expires_at TEXT
            );
            CREATE TABLE financial_cache (
                ticker TEXT, statement_type TEXT, payload TEXT,
                fetched_at TEXT, expires_at TEXT
            );
        """)
        connection.execute(
            "INSERT INTO company_metadata VALUES (?, ?, ?, ?)",
            ("AAPL", json.dumps({"is_adr": False}), now.isoformat(), (now + timedelta(days=1)).isoformat()),
        )
        connection.execute(
            "INSERT INTO financial_cache VALUES (?, ?, ?, ?, ?)",
            ("AAPL", "income_statement:annual", "[]", (now - timedelta(days=2)).isoformat(), (now - timedelta(days=1)).isoformat()),
        )

    result = load_financial_records(path, now=now)

    assert result.scanned == 2
    assert result.rejected == 0
    assert [(row.ticker, row.data_type) for row in result.records] == [
        ("AAPL", "company_metadata")
    ]


def test_news_backfill_merges_databases_and_keeps_newest_payload(tmp_path):
    now = datetime(2026, 7, 19, tzinfo=UTC)
    paths = [tmp_path / "one.db", tmp_path / "two.db"]
    for index, path in enumerate(paths, start=1):
        timestamp = int((now - timedelta(days=index)).timestamp())
        payload = {
            "id": index,
            "headline": f"Story version {index}",
            "summary": "Summary",
            "source": "Example",
            "timestamp": timestamp,
            "url": "https://example.com/story",
            "image": "",
            "topic": "Company",
            "relevance_score": 80,
        }
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE news_cache (ticker TEXT, published_at TEXT, payload TEXT)"
            )
            connection.execute(
                "INSERT INTO news_cache VALUES (?, ?, ?)",
                ("AAPL", datetime.fromtimestamp(timestamp, tz=UTC).isoformat(), json.dumps(payload)),
            )

    result = load_news_records(paths, cutoff=now - timedelta(days=30))

    assert result.scanned == 2
    assert len(result.records) == 1
    assert result.records[0].payload["id"] == 1
