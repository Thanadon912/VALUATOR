"""Backfill active SQLite caches into the backend-only Supabase tables."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes.news import NewsArticle  # noqa: E402
from app.core.validation import normalize_ticker  # noqa: E402
from app.repositories import NewsCacheRecord, get_cache_repository  # noqa: E402


@dataclass(frozen=True)
class FinancialBackfillRecord:
    ticker: str
    data_type: str
    payload: Any
    fetched_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LoadResult:
    records: Sequence[Any]
    scanned: int
    rejected: int


def _utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def load_financial_records(path: Path, *, now: datetime) -> LoadResult:
    records: dict[tuple[str, str], FinancialBackfillRecord] = {}
    scanned = 0
    rejected = 0
    if not path.exists():
        return LoadResult([], 0, 0)

    with _connection(path) as connection:
        sources = (
            (
                "company_metadata",
                "SELECT ticker, payload, fetched_at, expires_at FROM company_metadata",
            ),
            (
                None,
                "SELECT ticker, statement_type, payload, fetched_at, expires_at "
                "FROM financial_cache",
            ),
        )
        for fixed_type, query in sources:
            for row in connection.execute(query):
                scanned += 1
                try:
                    ticker = normalize_ticker(row["ticker"])
                    data_type = fixed_type or row["statement_type"]
                    payload = json.loads(row["payload"])
                    fetched_at = _utc_timestamp(row["fetched_at"])
                    expires_at = _utc_timestamp(row["expires_at"])
                    if expires_at <= now or expires_at <= fetched_at:
                        continue
                    record = FinancialBackfillRecord(
                        ticker=ticker,
                        data_type=data_type,
                        payload=payload,
                        fetched_at=fetched_at,
                        expires_at=expires_at,
                    )
                    key = (ticker, data_type)
                    existing = records.get(key)
                    if existing is None or existing.fetched_at < fetched_at:
                        records[key] = record
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    rejected += 1
    return LoadResult(list(records.values()), scanned, rejected)


def load_news_records(paths: Iterable[Path], *, cutoff: datetime) -> LoadResult:
    records: dict[tuple[str, str], NewsCacheRecord] = {}
    scanned = 0
    rejected = 0
    for path in paths:
        if not path.exists():
            continue
        with _connection(path) as connection:
            for row in connection.execute(
                "SELECT ticker, published_at, payload FROM news_cache"
            ):
                scanned += 1
                try:
                    ticker = normalize_ticker(row["ticker"])
                    stored_published_at = _utc_timestamp(row["published_at"])
                    if stored_published_at < cutoff:
                        continue
                    article = NewsArticle.model_validate(json.loads(row["payload"]))
                    published_at = datetime.fromtimestamp(
                        article.timestamp,
                        tz=timezone.utc,
                    )
                    if published_at < cutoff:
                        continue
                    record = NewsCacheRecord(
                        ticker=ticker,
                        url=article.url,
                        published_at=published_at,
                        payload=article.model_dump(),
                    )
                    key = (ticker, article.url)
                    existing = records.get(key)
                    if existing is None or existing.published_at < published_at:
                        records[key] = record
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
                    rejected += 1
    return LoadResult(list(records.values()), scanned, rejected)


def _batches(records: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(records), size):
        yield records[start : start + size]


async def _backfill(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    financial = load_financial_records(args.financial_db, now=now)
    news = load_news_records(
        args.news_db,
        cutoff=now - timedelta(days=30),
    )
    report: dict[str, Any] = {
        "dry_run": args.dry_run,
        "financial": {
            "scanned": financial.scanned,
            "eligible": len(financial.records),
            "rejected": financial.rejected,
        },
        "news": {
            "scanned": news.scanned,
            "eligible": len(news.records),
            "rejected": news.rejected,
        },
    }
    if args.dry_run:
        return report

    repository = await get_cache_repository()
    for record in financial.records:
        await repository.upsert_financial(
            record.ticker,
            record.data_type,
            record.payload,
            fetched_at=record.fetched_at,
            expires_at=record.expires_at,
        )
    for batch in _batches(news.records, args.batch_size):
        await repository.upsert_news(batch)

    verified_financial = 0
    for record in financial.records:
        cached = await repository.get_financial(
            record.ticker,
            record.data_type,
            now=now,
        )
        if cached is not None:
            verified_financial += 1

    expected_news: dict[str, set[str]] = {}
    for record in news.records:
        expected_news.setdefault(record.ticker, set()).add(record.url)
    verified_news = 0
    for ticker, urls in expected_news.items():
        payloads = await repository.list_news(
            ticker,
            cutoff=now - timedelta(days=30),
        )
        cached_urls = {
            payload.get("url") for payload in payloads if isinstance(payload, dict)
        }
        verified_news += len(urls & cached_urls)

    report["financial"]["verified"] = verified_financial
    report["news"]["verified"] = verified_news
    report["reconciled"] = (
        verified_financial == len(financial.records)
        and verified_news == len(news.records)
    )
    return report


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--financial-db",
        type=Path,
        default=BACKEND_ROOT / ".cache" / "financial_cache.sqlite3",
    )
    parser.add_argument(
        "--news-db",
        type=Path,
        action="append",
        default=None,
        help="Repeat to merge multiple legacy news databases.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.news_db is None:
        args.news_db = [
            PROJECT_ROOT / "news_cache.db",
            BACKEND_ROOT / "news_cache.db",
        ]
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    return args


def main() -> None:
    report = asyncio.run(_backfill(_arguments()))
    print(json.dumps(report, sort_keys=True))
    if not report.get("dry_run") and not report.get("reconciled"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
