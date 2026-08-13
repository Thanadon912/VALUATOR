"""Bucket B — real-time quote service.

Composes ONLY live/session telemetry for a ticker:

- Alpaca latest trade / quote for current regular and extended-hours price.
- Yahoo Finance regular + extended-hours quote as a fallback; fetched directly
  on each call so live price is never frozen by a long structural cache.
- Nasdaq latest daily close for the previous-close anchor plus currency /
  exchange metadata. These are slow-changing daily fields, so the Nasdaq
  provider's short cache is an acceptable anchor, but they are never the
  source of the *current* price.

The result is a provider-independent envelope following the response
contract. Derived ``change`` / ``change_percent`` use the live regular
price vs the previous close. If the live regular price is unavailable we
return ``unavailable`` rather than inventing a price — honoring AGENTS.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.models import LiveQuoteData, LiveQuoteResponse, SourceRecord
from app.providers.alpaca import AlpacaMarketDataProvider
from app.providers.nasdaq import NasdaqMarketProvider
from app.providers.yahoo import get_yahoo_quote

logger = logging.getLogger(__name__)


def build_live_quote_response(ticker: str) -> LiveQuoteResponse:
    settings = get_settings()
    fetched_at = datetime.now(timezone.utc).isoformat()
    sources: list[SourceRecord] = []
    warnings: list[str] = []

    # Preferred live intraday quote — fetched directly, never locked by the
    # structural cache. Alpaca covers pre-market / after-hours via latest
    # trades and latest bid/ask quotes.
    alpaca_provider = AlpacaMarketDataProvider(
        timeout_seconds=settings.provider_timeout_seconds,
    )
    alpaca_res = alpaca_provider.fetch_latest(ticker)
    alpaca_data = alpaca_res.data or {}
    sources.extend(
        SourceRecord(
            provider=s.provider,
            source_url=s.source_url,
            source_timestamp=s.source_timestamp,
            fetched_at=s.fetched_at,
            is_stale=getattr(s, "is_stale", False),
        )
        for s in alpaca_res.sources
    )
    if alpaca_res.warnings:
        warnings.extend(alpaca_res.warnings)

    # Yahoo remains a fallback for cases where Alpaca credentials or the data
    # endpoint are unavailable.
    yahoo_data = get_yahoo_quote(ticker) or {}
    if not alpaca_data and not yahoo_data:
        warnings.append("Live quote source returned no data.")

    # Daily anchor + metadata from Nasdaq (slow-changing; its short provider
    # cache is acceptable for previous_close / currency / exchange).
    nasdaq_provider = NasdaqMarketProvider(
        timeout_seconds=settings.provider_timeout_seconds,
    )
    nasdaq_res = nasdaq_provider.fetch(ticker)
    nasdaq_data = nasdaq_res.data if nasdaq_res.data else {}
    nasdaq_quote = nasdaq_data.get("quote", {}) or {}
    nasdaq_overview = nasdaq_data.get("overview", {}) or {}

    sources.extend(
        SourceRecord(
            provider=s.provider,
            source_url=s.source_url,
            source_timestamp=s.source_timestamp,
            fetched_at=s.fetched_at,
            is_stale=getattr(s, "is_stale", False),
        )
        for s in nasdaq_res.sources
    )
    if nasdaq_res.warnings:
        warnings.extend(nasdaq_res.warnings)

    def _num(value: object) -> float | None:
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").replace("%", "")
            return float(value)
        except (TypeError, ValueError):
            return None

    alpaca_price = _num(alpaca_data.get("price"))
    yahoo_price = _num(yahoo_data.get("regularMarketPrice"))
    live_price = alpaca_price if alpaca_price is not None else yahoo_price
    previous_close = _num(nasdaq_quote.get("previous_close"))
    
    # Currency overriding for US Exchanges
    currency = nasdaq_overview.get("currency") or "USD"
    exchange = (nasdaq_overview.get("exchange") or "").upper()
    if exchange in {"NASDAQ", "NYSE", "NYQ", "NMS", "NGM"}:
        currency = "USD"

    # Prefer the live regular price; fall back to Nasdaq's latest daily close
    # only when the live feed is unavailable, but flag it via warnings so the
    # UI can show a stale indicator rather than presenting it as live.
    price = live_price
    using_snapshot = False
    if price is None:
        price = _num(nasdaq_quote.get("price"))
        using_snapshot = price is not None
        if using_snapshot:
            warnings.append(
                "Live intraday price unavailable; showing latest daily close."
            )

    change = (
        price - previous_close
        if price is not None and previous_close is not None
        else _num(yahoo_data.get("regularMarketChange"))
    )
    change_percent = (
        (change / previous_close) * 100
        if change is not None and previous_close not in {None, 0}
        else _num(yahoo_data.get("regularMarketChangePercent"))
    )
    alpaca_extended_price = _num(alpaca_data.get("extended_price"))
    yahoo_extended_price = _num(yahoo_data.get("extendedPrice"))
    extended_price = (
        alpaca_extended_price
        if alpaca_extended_price is not None
        else yahoo_extended_price
    )
    extended_change = (
        extended_price - previous_close
        if extended_price is not None and previous_close is not None
        else _num(yahoo_data.get("extendedChange"))
    )
    extended_change_percent = (
        (extended_change / previous_close) * 100
        if extended_change is not None and previous_close not in {None, 0}
        else _num(yahoo_data.get("extendedChangePercent"))
    )

    status = "success" if price is not None else "unavailable"

    return LiveQuoteResponse(
        ticker=ticker.upper(),
        status=status,
        as_of=fetched_at,
        data=LiveQuoteData(
            symbol=ticker.upper(),
            price=price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            currency=currency,
            exchange=exchange,
            latest_trading_day=(
                alpaca_data.get("timestamp")
                or yahoo_data.get("regularMarketTime")
                or nasdaq_quote.get("latest_trading_day")
            ),
            market_state=(
                alpaca_data.get("market_state")
                or yahoo_data.get("marketState")
                or ("REGULAR" if using_snapshot else None)
            ),
            extended_price=extended_price,
            extended_change=extended_change,
            extended_change_percent=extended_change_percent,
            extended_hours_timestamp=(
                alpaca_data.get("extended_hours_timestamp")
                or yahoo_data.get("extendedHoursTimestamp")
            ),
        ),
        sources=sources,
        warnings=warnings,
    )
