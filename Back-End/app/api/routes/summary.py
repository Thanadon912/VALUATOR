from threading import Lock
from time import monotonic

from fastapi import APIRouter, HTTPException

from app.core.performance_cache import (
    is_performance_cache_only,
    raise_performance_cache_miss,
)
from app.core.validation import normalize_ticker
from app.models import SummaryResponse
from app.services.summary import build_summary_response


router = APIRouter(prefix="/api/stocks", tags=["summary"])

# Summary combines several live and structural providers. Keep the cache as
# short as the live quote cache, while coalescing concurrent requests for the
# same ticker so a traffic burst does not fan out into duplicate provider calls.
SUMMARY_CACHE_TTL_SECONDS = 8

_cache_lock = Lock()
_cache: dict[str, tuple[float, SummaryResponse]] = {}
_ticker_locks: dict[str, Lock] = {}


def _cached_summary(
    ticker: str,
    *,
    allow_stale: bool = False,
) -> SummaryResponse | None:
    with _cache_lock:
        cached = _cache.get(ticker)
        if cached and (
            allow_stale
            or monotonic() - cached[0] < SUMMARY_CACHE_TTL_SECONDS
        ):
            return cached[1]
    return None


def _ticker_lock(ticker: str) -> Lock:
    with _cache_lock:
        return _ticker_locks.setdefault(ticker, Lock())


@router.get("/{ticker}/summary", response_model=SummaryResponse)
def get_summary(ticker: str) -> SummaryResponse:
    try:
        normalized = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    key = normalized.upper()
    cache_only = is_performance_cache_only()
    cached = _cached_summary(key, allow_stale=cache_only)
    if cached is not None:
        return cached
    if cache_only:
        raise_performance_cache_miss("summary", key)

    # Double-check after waiting: another request may have populated the cache.
    with _ticker_lock(key):
        cached = _cached_summary(key)
        if cached is not None:
            return cached

        response = build_summary_response(normalized)
        with _cache_lock:
            _cache[key] = (monotonic(), response)
        return response
