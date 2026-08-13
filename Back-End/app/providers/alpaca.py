"""Alpaca market data provider for latest stock trade and quote telemetry."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.providers.base import ProviderResult, ProviderSource


ALPACA_LATEST_TRADES_URL = "https://data.alpaca.markets/v2/stocks/trades/latest"
ALPACA_LATEST_QUOTES_URL = "https://data.alpaca.markets/v2/stocks/quotes/latest"
DEFAULT_TIMEOUT_SECONDS = 8.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_timestamp(value: object) -> tuple[str | None, datetime | None]:
    if not isinstance(value, str) or not value:
        return None, None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    if "." in raw:
        prefix, suffix = raw.split(".", 1)
        tz_start = max(suffix.find("+"), suffix.find("-"))
        if tz_start >= 0:
            fraction = suffix[:tz_start]
            tz = suffix[tz_start:]
        else:
            fraction = suffix
            tz = ""
        raw = f"{prefix}.{fraction[:6]}{tz}"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return value, None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(), parsed


def _market_state(timestamp: datetime | None) -> str | None:
    if timestamp is None:
        return None
    eastern = timestamp.astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return "CLOSED"
    current = eastern.time()
    if time(4, 0) <= current < time(9, 30):
        return "PRE"
    if time(9, 30) <= current < time(16, 0):
        return "REGULAR"
    if time(16, 0) <= current < time(20, 0):
        return "POST"
    return "CLOSED"


def _record(payload: dict, key: str, symbol: str) -> dict:
    container = payload.get(key) or {}
    if isinstance(container, dict):
        item = container.get(symbol) or container.get(symbol.upper())
        if isinstance(item, dict):
            return item
    singular = key[:-1]
    item = payload.get(singular)
    return item if isinstance(item, dict) else {}


def _http_status_warning(prefix: str, exc: httpx.HTTPStatusError) -> str:
    return f"{prefix}: HTTP {exc.response.status_code}."


class AlpacaMarketDataProvider:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        data_feed: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.data_feed = data_feed
        self.timeout_seconds = timeout_seconds

    def _credentials(self) -> tuple[str | None, str | None, str | None]:
        settings = get_settings()
        return (
            self.api_key or settings.alpaca_api_key,
            self.api_secret or settings.alpaca_api_secret,
            self.data_feed or settings.alpaca_data_feed,
        )

    def _get_json(
        self,
        url: str,
        symbol: str,
        api_key: str,
        api_secret: str,
        data_feed: str | None,
    ) -> dict:
        params = {"symbols": symbol}
        if data_feed:
            params["feed"] = data_feed
        response = httpx.get(
            url,
            params=params,
            headers={
                "Accept": "application/json",
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def fetch_latest(self, ticker: str) -> ProviderResult:
        symbol = ticker.upper()
        fetched_at = _utc_now()
        api_key, api_secret, data_feed = self._credentials()
        if not api_key or not api_secret:
            return ProviderResult(
                data={},
                warnings=["Alpaca API key/secret not configured"],
            )

        warnings: list[str] = []
        trade: dict = {}
        quote: dict = {}

        try:
            trade_payload = self._get_json(
                ALPACA_LATEST_TRADES_URL,
                symbol,
                api_key,
                api_secret,
                data_feed,
            )
            trade = _record(trade_payload, "trades", symbol)
        except httpx.HTTPStatusError as exc:
            warnings.append(_http_status_warning("Alpaca latest trade request failed", exc))
        except (httpx.HTTPError, ValueError) as exc:
            warnings.append(f"Alpaca latest trade request failed: {exc.__class__.__name__}.")

        try:
            quote_payload = self._get_json(
                ALPACA_LATEST_QUOTES_URL,
                symbol,
                api_key,
                api_secret,
                data_feed,
            )
            quote = _record(quote_payload, "quotes", symbol)
        except httpx.HTTPStatusError as exc:
            warnings.append(_http_status_warning("Alpaca latest quote request failed", exc))
        except (httpx.HTTPError, ValueError) as exc:
            warnings.append(f"Alpaca latest quote request failed: {exc.__class__.__name__}.")

        trade_price = _num(trade.get("p"))
        bid_price = _num(quote.get("bp"))
        ask_price = _num(quote.get("ap"))
        midpoint = (
            (bid_price + ask_price) / 2
            if bid_price is not None and ask_price is not None and bid_price > 0 and ask_price > 0
            else bid_price
            if bid_price is not None and bid_price > 0
            else ask_price
            if ask_price is not None and ask_price > 0
            else None
        )

        price = trade_price if trade_price is not None else midpoint
        if price is None:
            if not warnings:
                warnings.append(f"Alpaca returned no latest trade or quote for {symbol}.")
            return ProviderResult(data={}, warnings=warnings)
        if trade_price is None and midpoint is not None:
            warnings.append("Alpaca latest trade unavailable; using latest quote price.")

        timestamp, parsed_timestamp = _normalize_timestamp(
            trade.get("t") if trade_price is not None else quote.get("t")
        )
        state = _market_state(parsed_timestamp)
        is_extended = state in {"PRE", "POST"}

        price_source = "trade" if trade_price is not None else "quote"
        source_url = (
            ALPACA_LATEST_TRADES_URL
            if trade_price is not None
            else ALPACA_LATEST_QUOTES_URL
        )
        source = ProviderSource(
            provider=f"Alpaca {price_source.title()}",
            source_url=source_url,
            source_timestamp=timestamp,
            fetched_at=fetched_at,
            is_stale=False,
        )

        return ProviderResult(
            data={
                "symbol": symbol,
                "price": price,
                "price_source": price_source,
                "timestamp": timestamp,
                "market_state": state,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "bid_size": _num(quote.get("bs")),
                "ask_size": _num(quote.get("as")),
                "extended_price": price if is_extended else None,
                "extended_hours_timestamp": timestamp if is_extended else None,
            },
            sources=[source],
            warnings=warnings,
        )
