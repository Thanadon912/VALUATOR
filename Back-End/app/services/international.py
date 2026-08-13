"""Auditable international-security normalization inputs."""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FX_CACHE_TTL_SECONDS = 6 * 60 * 60
_fx_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_fx_lock = Lock()
_fx_fetch_locks: dict[str, Lock] = {}


def _fx_fetch_lock(currency: str) -> Lock:
    with _fx_lock:
        return _fx_fetch_locks.setdefault(currency, Lock())

# Decimal additions to cost of equity. Unknown domiciles remain unavailable.
COUNTRY_RISK_PREMIUMS = {
    "US": 0.0, "USA": 0.0, "UNITED STATES": 0.0,
    "CA": 0.0, "CANADA": 0.0,
    "NL": 0.0, "NETHERLANDS": 0.0,
    "TW": 0.0075, "TAIWAN": 0.0075,
    "CN": 0.0125, "CHINA": 0.0125,
}
COUNTRY_RISK_PREMIUM_SOURCE = "Configured sovereign-risk table (Damodaran methodology)"
COUNTRY_RISK_PREMIUM_AS_OF = "2026-07-01"


def country_risk_premium(country: str | None) -> dict[str, Any] | None:
    normalized = (country or "").strip().upper()
    if normalized not in COUNTRY_RISK_PREMIUMS:
        return None
    return {
        "country": country,
        "country_risk_premium": COUNTRY_RISK_PREMIUMS[normalized],
        "source": COUNTRY_RISK_PREMIUM_SOURCE,
        "source_timestamp": COUNTRY_RISK_PREMIUM_AS_OF,
    }


def fetch_usd_fx_rate(reported_currency: str) -> dict[str, Any] | None:
    currency = reported_currency.strip().upper()
    if currency == "USD":
        return {"reported_currency": "USD", "valuation_currency": "USD", "rate": 1.0,
                "as_of": datetime.now(timezone.utc).date().isoformat(), "source": "identity conversion"}
    with _fx_lock:
        cached = _fx_cache.get(currency)
        if cached and monotonic() - cached[0] < FX_CACHE_TTL_SECONDS:
            return cached[1]

    with _fx_fetch_lock(currency):
        with _fx_lock:
            cached = _fx_cache.get(currency)
            if cached and monotonic() - cached[0] < FX_CACHE_TTL_SECONDS:
                return cached[1]
        try:
            response = httpx.get(
                YAHOO_CHART_URL.format(symbol=quote(f"{currency}USD=X", safe="")),
                params={"interval": "1d", "range": "5d"},
                headers={"User-Agent": "USAStockAnalysis/1.0"}, timeout=10.0,
            )
            response.raise_for_status()
            result = (response.json().get("chart", {}).get("result") or [None])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", []) if result else []
            observations = [(ts, float(close)) for ts, close in zip(result.get("timestamp", []), closes)
                            if close is not None and float(close) > 0] if result else []
            if not observations:
                return None
            timestamp, rate = observations[-1]
            payload = {"reported_currency": currency, "valuation_currency": "USD", "rate": rate,
                       "as_of": datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
                       "source": f"Yahoo Finance {currency}USD=X daily close"}
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None
        with _fx_lock:
            _fx_cache[currency] = (monotonic(), payload)
        return payload


def derive_adr_ratio(ordinary_shares: float | None, traded_shares: float | None) -> float | None:
    if not ordinary_shares or not traded_shares or ordinary_shares <= 0 or traded_shares <= 0:
        return None
    ratio = ordinary_shares / traded_shares
    rounded = round(ratio)
    return float(rounded) if rounded >= 1 and abs(ratio - rounded) / rounded <= 0.08 else None
