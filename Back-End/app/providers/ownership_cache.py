"""Ownership metrics cache (SQLite, 14-day TTL).

Caches Alpha Vantage COMPANY_OVERVIEW ownership values per ticker so the
free-tier 25 requests/day limit is never exhausted. Ownership data moves
slowly (it updates on SEC filing cycles), so a 14-day TTL is conservative
without serving stale data.

Pattern mirrors sec_customer_mix_cache.py (threading.Lock + atomic writes)
and sec_13f.py (sqlite3), but uses a small single-table SQLite store per the
approved statistics spec.

Schema is created lazily on first access. Writes are atomic via explicit
transactions. Reads return None when the row is missing OR older than the
TTL, so callers always treat the result as "fresh or nothing".
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.runtime_paths import runtime_cache_path


# Bucket A — Fundamental & Structural Cache (ownership/share structure).
# Updates on SEC filing cycles, so a 14-day TTL is conservative.
DEFAULT_TTL_DAYS = 14
_cache_lock = Lock()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ownership_metrics (
    ticker TEXT PRIMARY KEY,
    percent_insiders REAL,
    percent_institutions REAL,
    shares_outstanding REAL,
    forward_pe REAL,
    peg_ratio REAL,
    dividend_yield REAL,
    dividend_per_share REAL,
    payout_ratio REAL,
    quarterly_revenue_growth_yoy REAL,
    source TEXT,
    fetched_at TEXT NOT NULL
)
"""


def _default_db_path() -> Path:
    cache_dir = runtime_cache_path("ownership")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "ownership.sqlite3"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def get_cached(
    ticker: str,
    *,
    ttl_days: int = DEFAULT_TTL_DAYS,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return cached ownership metrics if present and within TTL, else None."""
    path = Path(db_path) if db_path else _default_db_path()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
    try:
        with _cache_lock:
            conn = _connect(path)
            try:
                row = conn.execute(
                    "SELECT percent_insiders, percent_institutions, "
                    "shares_outstanding, forward_pe, peg_ratio, "
                    "dividend_yield, dividend_per_share, payout_ratio, quarterly_revenue_growth_yoy, source, fetched_at "
                    "FROM ownership_metrics WHERE ticker = ? AND fetched_at > ?",
                    (ticker.upper(), cutoff),
                ).fetchone()
            finally:
                conn.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    percent_insiders, percent_institutions, shares_outstanding, forward_pe, peg_ratio, dividend_yield, dividend_per_share, payout_ratio, quarterly_revenue_growth_yoy, source, fetched_at = row
    return {
        "ticker": ticker.upper(),
        "percent_insiders": percent_insiders,
        "percent_institutions": percent_institutions,
        "shares_outstanding": shares_outstanding,
        "forward_pe": forward_pe,
        "peg_ratio": peg_ratio,
        "dividend_yield": dividend_yield,
        "dividend_per_share": dividend_per_share,
        "payout_ratio": payout_ratio,
        "quarterly_revenue_growth_yoy": quarterly_revenue_growth_yoy,
        "source": source,
        "fetched_at": fetched_at,
    }


def upsert(
    ticker: str,
    *,
    percent_insiders: float | None,
    percent_institutions: float | None,
    shares_outstanding: float | None,
    forward_pe: float | None = None,
    peg_ratio: float | None = None,
    dividend_yield: float | None = None,
    dividend_per_share: float | None = None,
    payout_ratio: float | None = None,
    quarterly_revenue_growth_yoy: float | None = None,
    source: str = "Alpha Vantage",
    fetched_at: str | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Insert or replace ownership metrics for a ticker with a fresh timestamp.

    All metric values may be None — a fetch that resolved only some fields is
    still cached (saves the API call) rather than forcing a refetch.
    """
    path = Path(db_path) if db_path else _default_db_path()
    timestamp = fetched_at or datetime.now(timezone.utc).isoformat()
    try:
        with _cache_lock:
            conn = _connect(path)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO ownership_metrics "
                    "(ticker, percent_insiders, percent_institutions, "
                    "shares_outstanding, forward_pe, peg_ratio, "
                    "dividend_yield, dividend_per_share, payout_ratio, "
                    "quarterly_revenue_growth_yoy, source, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        ticker.upper(),
                        percent_insiders,
                        percent_institutions,
                        shares_outstanding,
                        forward_pe,
                        peg_ratio,
                        dividend_yield,
                        dividend_per_share,
                        payout_ratio,
                        quarterly_revenue_growth_yoy,
                        source,
                        timestamp,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
    except sqlite3.Error:
        # Cache write failure must never break the statistics page; the
        # caller already has the data in memory for this request.
        pass
