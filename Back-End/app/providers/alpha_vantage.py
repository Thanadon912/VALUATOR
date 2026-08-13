"""Alpha Vantage OVERVIEW provider.

Fetches ownership and share-structure data from Alpha Vantage's free
``OVERVIEW`` endpoint (the current name; ``COMPANY_OVERVIEW`` is the legacy
name Alpha Vantage no longer recognises). The free tier is rate-limited
(25 requests/day), so callers MUST wrap this in the ownership cache layer
before use.

Returned data is intentionally raw — Alpha Vantage returns mixed numeric
conventions (e.g. ``PercentInsiders`` as a decimal like ``0.1462`` while
``SharesOutstanding`` is an integer count). Conversion to display percent
values happens in the service layer, not here.

Never invents values: a missing or rate-limited response returns an empty
``data`` dict with a warning, never a zero or fabricated number.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic

import httpx

from app.core.config import get_settings
from app.providers.base import ProviderResult, ProviderSource


ALPHA_VANTAGE_OVERVIEW_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_SOURCE_URL = "https://www.alphavantage.co"
DEFAULT_TIMEOUT_SECONDS = 10.0
ALPHA_VANTAGE_OVERVIEW_CACHE_TTL_SECONDS = 24 * 60 * 60
_cache_lock = Lock()
_overview_cache: dict[str, tuple[float, ProviderResult]] = {}
_fetch_locks: dict[str, Lock] = {}


def _fetch_lock(ticker: str) -> Lock:
    with _cache_lock:
        return _fetch_locks.setdefault(ticker, Lock())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_number(value: object) -> float | None:
    """Parse an Alpha Vantage value into a float, returning None on failure.

    Alpha Vantage returns most numeric fields as strings ("0.1462", "14687").
    ``None`` and the literal string ``"None"`` (which AV emits for missing
    fields) are treated as unavailable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"none", "null", "-"}:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


class AlphaVantageOverviewProvider:
    """Fetches COMPANY_OVERVIEW from Alpha Vantage."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _resolve_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        return get_settings().alpha_vantage_api_key

    def fetch(self, ticker: str) -> ProviderResult:
        normalized = ticker.upper()
        with _cache_lock:
            cached = _overview_cache.get(normalized)
            if cached and monotonic() - cached[0] < ALPHA_VANTAGE_OVERVIEW_CACHE_TTL_SECONDS:
                return cached[1]

        api_key = self._resolve_key()
        if not api_key:
            return ProviderResult(
                data={},
                warnings=["Alpha Vantage API key not configured"],
            )

        with _fetch_lock(normalized):
            with _cache_lock:
                cached = _overview_cache.get(normalized)
                if cached and monotonic() - cached[0] < ALPHA_VANTAGE_OVERVIEW_CACHE_TTL_SECONDS:
                    return cached[1]
            result = self._fetch_uncached(normalized, api_key)
            if result.data:
                with _cache_lock:
                    _overview_cache[normalized] = (monotonic(), result)
            return result

    def _fetch_uncached(self, ticker: str, api_key: str) -> ProviderResult:
        fetched_at = _utc_now()

        try:
            response = httpx.get(
                ALPHA_VANTAGE_OVERVIEW_URL,
                params={
                    "function": "OVERVIEW",
                    "symbol": ticker,
                    "apikey": api_key,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return ProviderResult(
                data={},
                warnings=[f"Alpha Vantage fetch failed: {exc.__class__.__name__}"],
            )
        except ValueError as exc:
            return ProviderResult(
                data={},
                warnings=[f"Alpha Vantage returned invalid JSON: {exc.__class__.__name__}"],
            )

        # Alpha Vantage signals rate-limit and informational messages via
        # top-level keys instead of HTTP status codes. HTTP 200 still carries
        # errors in the body, so these must be inspected explicitly.
        if not isinstance(payload, dict):
            return ProviderResult(
                data={},
                warnings=["Alpha Vantage returned a non-object response"],
            )
        error_message = payload.get("Error Message")
        if error_message:
            return ProviderResult(
                data={},
                warnings=[f"Alpha Vantage error: {error_message}"],
            )
        informational = payload.get("Information") or payload.get("Note")
        if informational:
            return ProviderResult(
                data={},
                warnings=[
                    f"Alpha Vantage rate-limit/information message: {informational}"
                ],
            )
        if not payload or "Symbol" not in payload:
            return ProviderResult(
                data={},
                warnings=[f"Alpha Vantage returned no overview data for {ticker}"],
            )

        # Extract the ownership / share-structure fields the statistics page
        # needs. Keep raw values; let the service layer convert conventions.
        percent_insiders = _parse_number(payload.get("PercentInsiders"))
        percent_institutions = _parse_number(payload.get("PercentInstitutions"))
        shares_outstanding = _parse_number(payload.get("SharesOutstanding"))
        market_cap = _parse_number(payload.get("MarketCapitalization"))
        beta = _parse_number(payload.get("Beta"))
        
        # Additional fields for valuation and dividends
        forward_pe = _parse_number(payload.get("ForwardPE"))
        peg_ratio = _parse_number(payload.get("PEGRatio"))
        dividend_yield = _parse_number(payload.get("DividendYield"))
        dividend_per_share = _parse_number(payload.get("DividendPerShare"))
        payout_ratio = _parse_number(payload.get("PayoutRatio"))
        quarterly_revenue_growth_yoy = _parse_number(payload.get("QuarterlyRevenueGrowthYOY"))

        data = {
            "symbol": payload.get("Symbol"),
            "name": payload.get("Name"),
            "reported_currency": payload.get("Currency"),
            "country": payload.get("Country"),
            "asset_type": payload.get("AssetType"),
            "percent_insiders": percent_insiders,
            "percent_institutions": percent_institutions,
            "shares_outstanding": shares_outstanding,
            "market_cap": market_cap,
            "beta": beta,
            "forward_pe": forward_pe,
            "peg_ratio": peg_ratio,
            "dividend_yield": dividend_yield,
            "dividend_per_share": dividend_per_share,
            "payout_ratio": payout_ratio,
            "quarterly_revenue_growth_yoy": quarterly_revenue_growth_yoy,
            "fetched_at": fetched_at,
        }

        source = ProviderSource(
            provider="Alpha Vantage",
            source_url=ALPHA_VANTAGE_SOURCE_URL,
            source_timestamp=None,
            fetched_at=fetched_at,
            is_stale=False,
        )
        return ProviderResult(data=data, sources=[source], warnings=[])
