from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import monotonic

import httpx

from app.providers.base import ProviderResult, ProviderSource


NASDAQ_HISTORICAL_URL = (
    "https://api.nasdaq.com/api/quote/{ticker}/historical"
)
NASDAQ_SUMMARY_URL = "https://api.nasdaq.com/api/quote/{ticker}/summary"
NASDAQ_DIVIDENDS_URL = "https://api.nasdaq.com/api/quote/{ticker}/dividends"

# Bucket A — Structural Cache.
# Historical price series, dividend events, and Nasdaq summary metadata
# (exchange, sector, market_cap, 52-week range) are slow-changing daily
# data. Cache for 14 days so page re-entry is instant.
NASDAQ_STRUCTURAL_CACHE_TTL_SECONDS = 14 * 24 * 60 * 60

_cache_lock = Lock()
# Caches the structural payload (price_history, dividends, overview) only.
# The live quote block is always augmented with fresh Yahoo data and is
# NEVER locked by this cache.
_structural_cache: dict[str, tuple[float, dict]] = {}
_structural_fetch_locks: dict[str, Lock] = {}


def _structural_fetch_lock(ticker: str) -> Lock:
    with _cache_lock:
        return _structural_fetch_locks.setdefault(ticker, Lock())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: str | None) -> float | None:
    if value in {None, "", "N/A", "-"}:
        return None
    normalized = value.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _iso_date(value: str) -> str:
    return datetime.strptime(value, "%m/%d/%Y").date().isoformat()


def _summary_value(payload: dict, key: str) -> str | None:
    value = (
        payload.get("data", {})
        .get("summaryData", {})
        .get(key, {})
        .get("value")
    )
    return value if isinstance(value, str) else None


class NasdaqMarketProvider:
    def __init__(self, timeout_seconds: float = 8) -> None:
        self.timeout_seconds = timeout_seconds
        self.headers = {
            "User-Agent": "Mozilla/5.0 USAStockAnalysis/1.0",
            "Accept": "application/json",
        }

    def fetch(self, ticker: str) -> ProviderResult:
        # ── 1. Load or build the structural payload (Bucket A) ─────
        structural = self._get_structural(ticker)
        if structural.get("error"):
            return ProviderResult(
                data=None,
                warnings=structural.get("warnings", []),
            )

        # ── 2. Fresh Yahoo quote augmentation (Bucket B) ──────────
        # Yahoo is fetched every call (no cache) so intraday price,
        # market state and extended-hours telemetry are never frozen
        # by the structural cache.
        from app.providers.yahoo import get_yahoo_quote
        yahoo_data = get_yahoo_quote(ticker)

        # ── 3. Compose the final result ────────────────────────────
        quote_block = {
            "symbol": ticker,
            **structural["quote_snapshot"],
            # Fresh live fields overwrite the stale snapshot counterparts
            "marketState": yahoo_data.get("marketState") or "REGULAR",
            "regularMarketPrice": yahoo_data.get("regularMarketPrice"),
            "regularMarketChangePercent": yahoo_data.get(
                "regularMarketChangePercent"
            ),
            "extendedPrice": yahoo_data.get("extendedPrice"),
            "extendedChange": yahoo_data.get("extendedChange"),
            "extendedChangePercent": yahoo_data.get("extendedChangePercent"),
            "extendedHoursTimestamp": yahoo_data.get("extendedHoursTimestamp"),
        }
        # Prefer the live regular price for the primary "price" field when
        # available so derived metrics (market cap, ratios) use a fresh value.
        if yahoo_data.get("regularMarketPrice") is not None:
            quote_block["price"] = yahoo_data["regularMarketPrice"]
            prev = structural["quote_snapshot"].get("previous_close")
            if prev is not None:
                quote_block["change"] = yahoo_data["regularMarketPrice"] - prev
                quote_block["change_percent"] = (
                    (quote_block["change"] / prev) * 100 if prev != 0 else None
                )

        return ProviderResult(
            data={
                "quote": quote_block,
                "interval": "daily",
                "price_history": structural["price_history"],
                "dividends": structural["dividends"],
                "dividend_coverage": structural["dividend_coverage"],
                "overview": structural["overview"],
            },
            sources=structural["sources"],
            warnings=structural["warnings"],
        )

    def _get_structural(self, ticker: str) -> dict:
        """Return (or build and cache) the structural Nasdaq payload.

        Covers: price history, dividend events, Nasdaq summary metadata,
        and a daily-close quote snapshot (previous_close, 52-week range).
        This data is Bucket A and cached for 14 days.
        """
        with _cache_lock:
            cached = _structural_cache.get(ticker)
            if cached and monotonic() - cached[0] < NASDAQ_STRUCTURAL_CACHE_TTL_SECONDS:
                return cached[1]

        with _structural_fetch_lock(ticker):
            with _cache_lock:
                cached = _structural_cache.get(ticker)
                if cached and monotonic() - cached[0] < NASDAQ_STRUCTURAL_CACHE_TTL_SECONDS:
                    return cached[1]
            return self._fetch_structural(ticker)

    def _fetch_structural(self, ticker: str) -> dict:

        source_url = NASDAQ_HISTORICAL_URL.format(ticker=ticker)
        summary_url = NASDAQ_SUMMARY_URL.format(ticker=ticker)
        dividends_url = NASDAQ_DIVIDENDS_URL.format(ticker=ticker)
        from_date = (date.today() - timedelta(days=365 * 5 + 10)).isoformat()
        fetched_at = _utc_now()
        warnings: list[str] = []

        try:
            response = httpx.get(
                source_url,
                params={
                    "assetclass": "stocks",
                    "fromdate": from_date,
                    "limit": 5000,
                },
                headers=self.headers,
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
            rows = (
                payload.get("data", {})
                .get("tradesTable", {})
                .get("rows", [])
            )
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            return {
                "error": True,
                "warnings": [f"Nasdaq market request failed: {exc.__class__.__name__}."],
            }

        summary_payload: dict = {}
        summary_succeeded = False
        try:
            summary_response = httpx.get(
                summary_url,
                params={"assetclass": "stocks"},
                headers=self.headers,
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            summary_response.raise_for_status()
            summary_payload = summary_response.json()
            summary_succeeded = True
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            warnings.append(
                f"Nasdaq summary request failed: {exc.__class__.__name__}."
            )

        dividend_payload: dict = {}
        dividends_succeeded = False
        try:
            dividend_response = httpx.get(
                dividends_url,
                params={"assetclass": "stocks"},
                headers=self.headers,
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            dividend_response.raise_for_status()
            dividend_payload = dividend_response.json()
            dividends_succeeded = True
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            warnings.append(
                f"Nasdaq dividends request failed: {exc.__class__.__name__}."
            )

        points = [
            {
                "date": _iso_date(row["date"]),
                "open": _number(row.get("open")),
                "high": _number(row.get("high")),
                "low": _number(row.get("low")),
                "close": _number(row.get("close")),
                "volume": _number(row.get("volume")),
            }
            for row in reversed(rows)
            if row.get("date")
        ]
        valid = [point for point in points if point["close"] is not None]
        if not valid:
            return {
                "error": True,
                "warnings": [f"Nasdaq returned no historical prices for {ticker}."],
            }

        latest = valid[-1]
        previous = valid[-2] if len(valid) > 1 else None
        previous_close = previous["close"] if previous else None
        change = (
            latest["close"] - previous_close
            if previous_close is not None
            else None
        )
        change_percent = (
            (change / previous_close) * 100
            if change is not None and previous_close not in {None, 0}
            else None
        )
        trailing_year = valid[-252:]
        week_52_low = min(
            (point["low"] for point in trailing_year if point["low"] is not None),
            default=None,
        )
        week_52_high = max(
            (point["high"] for point in trailing_year if point["high"] is not None),
            default=None,
        )
        dividend_data = dividend_payload.get("data") or {}
        dividend_rows = (
            dividend_data.get("dividends") or {}
        ).get("rows") or []
        dividends = sorted(
            [
                {
                    "ex_date": _iso_date(row["exOrEffDate"]),
                    "amount": _number(row.get("amount")),
                    "currency": row.get("currency"),
                    "type": row.get("type"),
                    "declaration_date": (
                        _iso_date(row["declarationDate"])
                        if row.get("declarationDate") not in {None, "N/A"}
                        else None
                    ),
                    "payment_date": (
                        _iso_date(row["paymentDate"])
                        if row.get("paymentDate") not in {None, "N/A"}
                        else None
                    ),
                }
                for row in dividend_rows
                if (
                    row.get("exOrEffDate") not in {None, "N/A"}
                    and _number(row.get("amount")) is not None
                )
            ],
            key=lambda item: item["ex_date"],
        )

        # ── Build structural dict (no live intraday fields) ─────────
        sources = [
            ProviderSource(
                provider="Nasdaq",
                source_url=source_url,
                source_timestamp=latest["date"],
                fetched_at=fetched_at,
            )
        ]
        if summary_succeeded:
            sources.append(
                ProviderSource(
                    provider="Nasdaq Summary",
                    source_url=summary_url,
                    source_timestamp=latest["date"],
                    fetched_at=fetched_at,
                )
            )
        if dividends_succeeded:
            sources.append(
                ProviderSource(
                    provider="Nasdaq Dividends",
                    source_url=dividends_url,
                    source_timestamp=(
                        dividends[-1]["ex_date"] if dividends else None
                    ),
                    fetched_at=fetched_at,
                )
            )

        structural = {
            "error": False,
            "quote_snapshot": {
                "symbol": ticker,
                "price": latest["close"],
                "previous_close": previous_close,
                "change": change,
                "change_percent": change_percent,
                "latest_trading_day": latest["date"],
                "period_low": latest["low"],
                "period_high": latest["high"],
                "range_label": "Day range",
            },
            "price_history": valid,
            "dividends": dividends,
            "dividend_coverage": (
                "reported_events"
                if dividends
                else "no_reported_events"
                if dividends_succeeded
                else "unavailable"
            ),
            "overview": {
                "name": payload.get("data", {}).get("symbol"),
                "description": None,
                "exchange": _summary_value(summary_payload, "Exchange"),
                "currency": "USD",
                "sector": _summary_value(summary_payload, "Sector"),
                "industry": _summary_value(summary_payload, "Industry"),
                "market_cap": _number(
                    _summary_value(summary_payload, "MarketCap")
                ),
                "market_cap_basis": (
                    "Nasdaq-reported market capitalization"
                    if _number(_summary_value(summary_payload, "MarketCap"))
                    is not None
                    else None
                ),
                "pe_ratio": None,
                "forward_pe": None,
                "price_to_sales": None,
                "ev_to_ebitda": None,
                "eps": None,
                "dividend_yield": None,
                "week_52_high": week_52_high,
                "week_52_low": week_52_low,
            },
            "sources": sources,
            "warnings": warnings,
        }

        with _cache_lock:
            _structural_cache[ticker] = (monotonic(), structural)
        return structural
