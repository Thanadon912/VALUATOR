import os
import httpx
from threading import Lock
from time import monotonic
from typing import Any
from app.providers.base import ProviderResult

FINNHUB_METRIC_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache_lock = Lock()
_metric_cache: dict[str, tuple[float, ProviderResult]] = {}
_fetch_locks: dict[str, Lock] = {}


def _fetch_lock(ticker: str) -> Lock:
    with _cache_lock:
        return _fetch_locks.setdefault(ticker, Lock())

class FinnhubMetricProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        self.url = "https://finnhub.io/api/v1/stock/metric"

    def fetch(self, ticker: str) -> ProviderResult:
        normalized = ticker.upper()
        with _cache_lock:
            cached = _metric_cache.get(normalized)
            if cached and monotonic() - cached[0] < FINNHUB_METRIC_CACHE_TTL_SECONDS:
                return cached[1]
        if not self.api_key:
            return ProviderResult(data={}, warnings=["Finnhub API key not configured"])
        with _fetch_lock(normalized):
            with _cache_lock:
                cached = _metric_cache.get(normalized)
                if cached and monotonic() - cached[0] < FINNHUB_METRIC_CACHE_TTL_SECONDS:
                    return cached[1]
            try:
                res = httpx.get(
                    self.url,
                    params={"symbol": normalized, "metric": "all", "token": self.api_key},
                    timeout=8.0
                )
                res.raise_for_status()
                data = res.json().get("metric", {})
                result = ProviderResult(data=data, warnings=[])
                if data:
                    with _cache_lock:
                        _metric_cache[normalized] = (monotonic(), result)
                return result
            except httpx.HTTPStatusError as exc:
                return ProviderResult(
                    data={},
                    warnings=[f"Finnhub metrics fetch failed: HTTP {exc.response.status_code}"],
                )
            except Exception as exc:
                return ProviderResult(
                    data={},
                    warnings=[f"Finnhub metrics fetch failed: {type(exc).__name__}"],
                )

def fetch_finnhub_metrics(ticker: str) -> dict[str, Any] | None:
    provider = FinnhubMetricProvider()
    res = provider.fetch(ticker)
    if not res.data:
        return None
    # Usually metric keys like "revenueTTM", "netIncomeTTM" etc.
    # Note: Finnhub values are usually in millions.
    return {
        "revenue_ttm": res.data.get("revenueTTM"),
        "net_income_ttm": res.data.get("netIncomeTTM"),
    }

def fetch_peer_metrics(tickers: list[str]) -> list[dict[str, Any]]:
    provider = FinnhubMetricProvider()
    real_peers = []
    for t in tickers:
        try:
            res = provider.fetch(t)
            if res.data:
                pe = res.data.get("peExclExtraTTM") or res.data.get("peBasicExclExtraTTM") or 0.0
                pb = res.data.get("pbAnnual") or res.data.get("pbQuarterly") or 0.0
                ev_ebitda = res.data.get("enterpriseValueOverEBITDATTM") or 0.0
                if pe or pb or ev_ebitda:
                    real_peers.append({
                        "symbol": t,
                        "name": t,
                        "pe": float(pe),
                        "pb": float(pb),
                        "ev_ebitda": float(ev_ebitda)
                    })
        except Exception:
            pass
    return real_peers
