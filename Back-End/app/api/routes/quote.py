from __future__ import annotations

from threading import Lock
from time import monotonic

from fastapi import APIRouter, HTTPException, Query

from app.core.performance_cache import (
    is_performance_cache_only,
    raise_performance_cache_miss,
)
from app.core.validation import normalize_ticker
from app.models import LiveQuoteResponse, StockSnapshotsResponse
from app.services.market_snapshots import build_market_snapshots
from app.services.quote import build_live_quote_response


router = APIRouter(prefix="/api/stocks", tags=["quote"])

# Bucket B — Real-Time & Live Stream cache.
# Strictly short: under the 10-second max. Only exists to dedupe rapid tab
# switches / concurrent requests for the same ticker. Live price telemetry
# must never be locked by the long structural (Bucket A) caches.
LIVE_QUOTE_CACHE_TTL_SECONDS = 8

_cache_lock = Lock()
_cache: dict[str, tuple[float, LiveQuoteResponse]] = {}
_ticker_locks: dict[str, Lock] = {}


def _ticker_lock(ticker: str) -> Lock:
    with _cache_lock:
        return _ticker_locks.setdefault(ticker, Lock())


def _parse_snapshot_tickers(raw_tickers: str) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    for raw_ticker in raw_tickers.split(","):
        if not raw_ticker.strip():
            raise ValueError(
                "Tickers must be a comma-separated list without empty values."
            )
        normalized = normalize_ticker(raw_ticker)
        if normalized not in seen:
            seen.add(normalized)
            tickers.append(normalized)
    if len(tickers) > 20:
        raise ValueError("A maximum of 20 unique tickers is allowed per request.")
    return tickers


@router.get("/{ticker}/quote", response_model=LiveQuoteResponse)
def get_live_quote(ticker: str) -> LiveQuoteResponse:
    try:
        normalized = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    key = normalized.upper()
    cache_only = is_performance_cache_only()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and (
            cache_only
            or monotonic() - cached[0] < LIVE_QUOTE_CACHE_TTL_SECONDS
        ):
            return cached[1]
    if cache_only:
        raise_performance_cache_miss("quote", key)

    with _ticker_lock(key):
        with _cache_lock:
            cached = _cache.get(key)
            if cached and monotonic() - cached[0] < LIVE_QUOTE_CACHE_TTL_SECONDS:
                return cached[1]

        response = build_live_quote_response(normalized)

        # Only cache successful/partial responses. An unavailable response
        # means the provider had nothing this instant; do not serve it stale.
        if response.status in {"success", "partial"}:
            with _cache_lock:
                _cache[key] = (monotonic(), response)
        return response


@router.get("/snapshots", response_model=StockSnapshotsResponse)
def get_stock_snapshots(
    tickers: str = Query(..., min_length=1),
) -> StockSnapshotsResponse:
    try:
        normalized = _parse_snapshot_tickers(tickers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return build_market_snapshots(
        normalized,
        get_live_quote,
        concurrent=not is_performance_cache_only(),
    )
