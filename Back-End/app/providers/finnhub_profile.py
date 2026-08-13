from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import monotonic, sleep
from typing import Any

import httpx

from app.providers.base import ProviderResult, ProviderSource


FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_EARNINGS_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/earnings"
FINNHUB_SOURCE_URL = "https://finnhub.io"
RATE_LIMIT_COOLDOWN_SECONDS = 60
FINNHUB_STRUCTURAL_PROFILE_CACHE_TTL_SECONDS = 24 * 60 * 60

_cooldown_lock = Lock()
_cooldown_until = 0.0
_profile_cache_lock = Lock()
_structural_profile_cache: dict[str, tuple[float, ProviderResult]] = {}
_structural_profile_locks: dict[str, Lock] = {}


def _structural_profile_lock(ticker: str) -> Lock:
    with _profile_cache_lock:
        return _structural_profile_locks.setdefault(ticker, Lock())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field(
    value: str | int | float | None,
    *,
    source_url: str,
    fetched_at: str,
    confidence: float = 0.95,
) -> dict[str, Any]:
    return {
        "value": value,
        "provider": "Finnhub",
        "source_url": source_url,
        "fetched_at": fetched_at,
        "confidence": confidence,
    }


def _number(value: Any, *, allow_zero: bool = True) -> float | None:
    if not isinstance(value, int | float):
        return None
    if not allow_zero and value == 0:
        return None
    return float(value)


def _quote_timestamp(payload: dict[str, Any]) -> str | None:
    timestamp = payload.get("t")
    if not isinstance(timestamp, int | float) or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _set_cooldown() -> None:
    global _cooldown_until
    with _cooldown_lock:
        _cooldown_until = monotonic() + RATE_LIMIT_COOLDOWN_SECONDS


def _in_cooldown() -> bool:
    with _cooldown_lock:
        return monotonic() < _cooldown_until


class FinnhubProfileProvider:
    def __init__(
        self,
        api_key: str | None,
        timeout_seconds: float = 8,
        max_retries: int = 1,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _get(self, url: str, params: dict[str, Any]) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            response = httpx.get(
                url,
                params={**params, "token": self.api_key},
                timeout=self.timeout_seconds,
            )
            last_response = response
            if response.status_code == 429:
                _set_cooldown()
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt < self.max_retries:
                sleep(0.25 * (attempt + 1))
        if last_response is None:
            raise httpx.HTTPError("Finnhub request did not return a response.")
        return last_response

    def fetch_structural_profile(self, ticker: str) -> ProviderResult:
        """Fetch only slow-changing profile fields, never quote/calendar data."""
        normalized = ticker.upper()
        with _profile_cache_lock:
            cached = _structural_profile_cache.get(normalized)
            if cached and monotonic() - cached[0] < FINNHUB_STRUCTURAL_PROFILE_CACHE_TTL_SECONDS:
                return cached[1]
        if not self.api_key:
            return ProviderResult(data={"fields": {}}, warnings=["Finnhub API key not configured"])
        if _in_cooldown():
            return ProviderResult(data={"fields": {}}, warnings=["Finnhub rate limit cooldown active"])

        with _structural_profile_lock(normalized):
            with _profile_cache_lock:
                cached = _structural_profile_cache.get(normalized)
                if cached and monotonic() - cached[0] < FINNHUB_STRUCTURAL_PROFILE_CACHE_TTL_SECONDS:
                    return cached[1]
            fetched_at = _utc_now()
            try:
                response = self._get(FINNHUB_PROFILE_URL, {"symbol": normalized})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not payload:
                    raise ValueError("Finnhub returned an empty profile")
            except (httpx.HTTPError, ValueError) as exc:
                return ProviderResult(
                    data={"fields": {}},
                    warnings=[f"Finnhub profile request failed: {exc.__class__.__name__}."],
                )

            fields = {
                "country": _field(payload.get("country"), source_url=FINNHUB_PROFILE_URL, fetched_at=fetched_at),
                "currency": _field(payload.get("currency"), source_url=FINNHUB_PROFILE_URL, fetched_at=fetched_at),
                "finnhub_industry": _field(payload.get("finnhubIndustry"), source_url=FINNHUB_PROFILE_URL, fetched_at=fetched_at),
            }
            result = ProviderResult(
                data={"fields": fields},
                sources=[ProviderSource(
                    provider="Finnhub",
                    source_url=FINNHUB_SOURCE_URL,
                    source_timestamp=None,
                    fetched_at=fetched_at,
                )],
            )
            with _profile_cache_lock:
                _structural_profile_cache[normalized] = (monotonic(), result)
            return result

    def fetch(self, ticker: str) -> ProviderResult:
        fetched_at = _utc_now()
        if not self.api_key:
            return ProviderResult(
                data={
                    "fields": {},
                    "quote": {},
                    "upcoming_events": [],
                    "unavailable": ["Finnhub API key not configured"],
                },
                warnings=["Finnhub API key not configured"],
            )
        if _in_cooldown():
            return ProviderResult(
                data={
                    "fields": {},
                    "quote": {},
                    "upcoming_events": [],
                    "unavailable": ["Finnhub rate limit cooldown active"],
                },
                warnings=["Finnhub rate limit cooldown active"],
            )

        try:
            profile_response = self._get(
                FINNHUB_PROFILE_URL,
                {"symbol": ticker},
            )
            profile_response.raise_for_status()
            profile_payload = profile_response.json()
            quote_payload: dict[str, Any] = {}
            quote_warnings: list[str] = []
            try:
                quote_response = self._get(
                    FINNHUB_QUOTE_URL,
                    {"symbol": ticker},
                )
                quote_response.raise_for_status()
                quote_payload = quote_response.json()
            except (httpx.HTTPError, ValueError) as exc:
                quote_payload = {}
                quote_warnings.append(
                    f"Finnhub quote request failed: {exc.__class__.__name__}."
                )
            events_payload: dict[str, Any] = {}
            today = date.today()
            try:
                events_response = self._get(
                    FINNHUB_EARNINGS_CALENDAR_URL,
                    {
                        "symbol": ticker,
                        "from": today.isoformat(),
                        "to": (today + timedelta(days=180)).isoformat(),
                    },
                )
                events_response.raise_for_status()
                events_payload = events_response.json()
            except httpx.HTTPError:
                events_payload = {}
        except (httpx.HTTPError, ValueError) as exc:
            return ProviderResult(
                data={
                    "fields": {},
                    "quote": {},
                    "upcoming_events": [],
                    "unavailable": [
                        f"Finnhub profile request failed: {exc.__class__.__name__}"
                    ],
                },
                warnings=[
                    f"Finnhub profile request failed: {exc.__class__.__name__}."
                ],
            )

        from app.providers.yahoo import get_yahoo_quote
        yahoo_data = get_yahoo_quote(ticker)

        quote = {
            "current_price": _field(
                _number(quote_payload.get("regularMarketPrice") or quote_payload.get("c"), allow_zero=False),
                source_url=FINNHUB_QUOTE_URL,
                fetched_at=fetched_at,
                confidence=0.9,
            ),
            "price_change": _field(
                _number(quote_payload.get("regularMarketChange") or quote_payload.get("d")),
                source_url=FINNHUB_QUOTE_URL,
                fetched_at=fetched_at,
                confidence=0.9,
            ),
            "price_change_percent": _field(
                _number(quote_payload.get("regularMarketChangePercent") or quote_payload.get("dp")),
                source_url=FINNHUB_QUOTE_URL,
                fetched_at=fetched_at,
                confidence=0.9,
            ),
            "previous_close": _field(
                _number(quote_payload.get("pc"), allow_zero=False),
                source_url=FINNHUB_QUOTE_URL,
                fetched_at=fetched_at,
                confidence=0.9,
            ),
            "extended_price": _field(
                yahoo_data.get("extendedPrice"),
                source_url="https://finance.yahoo.com",
                fetched_at=fetched_at,
                confidence=0.9,
            ),
            "extended_change": _field(
                yahoo_data.get("extendedChange"),
                source_url="https://finance.yahoo.com",
                fetched_at=fetched_at,
                confidence=0.9,
            ),
            "extended_change_percent": _field(
                yahoo_data.get("extendedChangePercent"),
                source_url="https://finance.yahoo.com",
                fetched_at=fetched_at,
                confidence=0.9,
            ),
        }
        quote["source_timestamp"] = _quote_timestamp(quote_payload)
        quote["market_state"] = yahoo_data.get("marketState") or quote_payload.get("marketState")
        quote["extended_hours_timestamp"] = yahoo_data.get("extendedHoursTimestamp") or quote_payload.get("extendedHoursTimestamp")
        unavailable = []
        if quote["current_price"]["value"] is None:
            unavailable.append("Finnhub quote unavailable")

        # Clearbit Logo Logic
        import re
        website = profile_payload.get("weburl")
        clean_domain = None
        if website:
            clean_domain = re.sub(r"^https?://(www\.)?", "", website.lower()).split("/")[0]
        
        logo_url = f"https://logo.clearbit.com/{clean_domain}" if clean_domain else None
        fmp_logo_url = profile_payload.get("logo")

        fields = {
            "website": _field(
                website,
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "logo": _field(
                fmp_logo_url,
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "logo_url": _field(
                logo_url,
                source_url="https://clearbit.com",
                fetched_at=fetched_at,
            ),
            "fmp_logo_url": _field(
                fmp_logo_url,
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "country": _field(
                profile_payload.get("country"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "currency": _field(
                profile_payload.get("currency"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "exchange": _field(
                profile_payload.get("exchange"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "ipo_date": _field(
                profile_payload.get("ipo"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "market_capitalization": _field(
                profile_payload.get("marketCapitalization"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "finnhub_industry": _field(
                profile_payload.get("finnhubIndustry"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
            ),
            "description": _field(
                profile_payload.get("description"),
                source_url=FINNHUB_PROFILE_URL,
                fetched_at=fetched_at,
                confidence=0.75,
            ),
        }
        events = []
        for item in events_payload.get("earningsCalendar", [])[:5]:
            event_date = item.get("date")
            if not event_date:
                continue
            events.append(
                {
                    "event_type": "earnings",
                    "title": "Earnings date",
                    "event_date": event_date,
                    "provider": "Finnhub",
                    "source": "Finnhub earnings calendar",
                    "source_url": FINNHUB_EARNINGS_CALENDAR_URL,
                    "fetched_at": fetched_at,
                    "confidence": 0.85,
                }
            )

        return ProviderResult(
            data={
                "fields": fields,
                "quote": quote,
                "upcoming_events": events,
                "unavailable": unavailable,
            },
            sources=[
                ProviderSource(
                    provider="Finnhub",
                    source_url=FINNHUB_SOURCE_URL,
                    source_timestamp=None,
                    fetched_at=fetched_at,
                )
            ],
            warnings=quote_warnings,
        )
