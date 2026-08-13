"""Financial Modeling Prep ingestion with earnings-aware Supabase caching."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable

import httpx

from app.core.config import get_settings
from app.repositories import FinancialCacheRepository, get_cache_repository


FMP_STABLE_BASE_URL = "https://financialmodelingprep.com/stable"
STATEMENT_ENDPOINTS = {
    "income_statement": "income-statement",
    "balance_sheet": "balance-sheet-statement",
    "cash_flow": "cash-flow-statement",
}
METADATA_TTL = timedelta(days=30)
EARNINGS_WINDOW = timedelta(days=7)
EARNINGS_WINDOW_STATEMENT_TTL = timedelta(hours=12)
OFF_SEASON_STATEMENT_TTL = timedelta(days=7)
ANALYST_ESTIMATES_TTL = timedelta(days=7)
STATIC_ADR_MAP = {
    "TSM": 5.0,
    "BABA": 8.0,
    "ASML": 1.0,
    "BIDU": 8.0,
    "JD": 2.0,
    "PDD": 4.0,
    "NVO": 1.0,
    "SONY": 1.0,
}

_locks_guard = Lock()
_ticker_locks: dict[str, Lock] = {}
logger = logging.getLogger(__name__)


def statement_ttl(now: datetime, next_earnings_date: date | None) -> timedelta:
    """Return 12h inside inclusive +/-7-day window, otherwise seven days."""
    if next_earnings_date is not None and abs((next_earnings_date - now.date()).days) <= EARNINGS_WINDOW.days:
        return EARNINGS_WINDOW_STATEMENT_TTL
    return OFF_SEASON_STATEMENT_TTL


def _ticker_lock(ticker: str) -> Lock:
    with _locks_guard:
        return _ticker_locks.setdefault(ticker, Lock())


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _next_earnings_date(rows: Any, today: date) -> date | None:
    if not isinstance(rows, list):
        return None
    dates = sorted(
        parsed for row in rows if isinstance(row, dict)
        if (parsed := _parse_date(row.get("date"))) is not None and parsed >= today - EARNINGS_WINDOW
    )
    return dates[0] if dates else None


def _reported_currency_from_statements(
    statements: dict[str, dict[str, list[dict[str, Any]]]],
) -> str | None:
    """Return the filing currency FMP reports statement rows in.

    Analyst-estimate rows are returned in this same currency (FMP does not
    convert consensus figures to USD), so callers must normalize before
    mixing estimates with USD-denominated inputs.
    """
    for statement_type in ("income_statement", "balance_sheet", "cash_flow"):
        for reports in (
            statements.get(statement_type, {}).get("annual", []),
            statements.get(statement_type, {}).get("quarterly", []),
        ):
            for report in reports:
                if isinstance(report, dict) and report.get("reportedCurrency"):
                    return str(report["reportedCurrency"]).upper()
    return None


def _apply_adr_fallback(ticker: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Resolve ADR ratio from FMP, then architect-approved static fallback."""
    normalized = ticker.upper()
    ratio = metadata.get("adr_ratio")
    try:
        ratio = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        ratio = None
    if ratio is not None and ratio > 0 and metadata.get("adr_ratio_source") == "fmp_sec_profile":
        return metadata

    resolved = dict(metadata)
    if normalized in STATIC_ADR_MAP:
        resolved.update({
            "is_adr": True,
            "adr_ratio": STATIC_ADR_MAP[normalized],
            "adr_ratio_source": "static_adr_map",
        })
    else:
        resolved.update({
            "adr_ratio": 1.0,
            "adr_ratio_source": "default_ordinary_share_ratio",
        })
    return resolved


class FMPFinancialsProvider:
    """Fetch annual and quarterly statements, caching each independently."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        cache: FinancialCacheRepository | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.fmp_api_key
        self.timeout_seconds = timeout_seconds or settings.provider_timeout_seconds
        self.cache = cache
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cache_warnings: set[str] = set()

    async def _cache_repository(self) -> FinancialCacheRepository:
        if self.cache is None:
            self.cache = await get_cache_repository()
        return self.cache

    async def _cache_get(
        self,
        ticker: str,
        data_type: str,
        *,
        now: datetime,
    ):
        try:
            repository = await self._cache_repository()
            return await repository.get_financial(ticker, data_type, now=now)
        except Exception:
            self._cache_warnings.add("SUPABASE_CACHE_READ_UNAVAILABLE")
            logger.warning(
                "supabase_cache_read_unavailable",
                extra={"cache_kind": "financial", "ticker": ticker.upper()},
            )
            return None

    async def _cache_put(
        self,
        ticker: str,
        data_type: str,
        payload: Any,
        *,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None:
        try:
            repository = await self._cache_repository()
            await repository.upsert_financial(
                ticker,
                data_type,
                payload,
                fetched_at=fetched_at,
                expires_at=expires_at,
            )
        except Exception:
            self._cache_warnings.add("SUPABASE_CACHE_WRITE_UNAVAILABLE")
            logger.warning(
                "supabase_cache_write_unavailable",
                extra={"cache_kind": "financial", "ticker": ticker.upper()},
            )

    async def _get_json(self, client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Any:
        response = await client.get(url, params={**params, "apikey": self.api_key}, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and (payload.get("Error Message") or payload.get("error")):
            raise ValueError(f"FMP error: {payload.get('Error Message') or payload.get('error')}")
        return payload

    async def _fetch_metadata(self, client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
        now = self._now()
        cached = await self._cache_get(ticker, "company_metadata", now=now)
        if cached is not None:
            metadata = _apply_adr_fallback(ticker, cached.payload)
            if metadata != cached.payload:
                await self._cache_put(
                    ticker,
                    "company_metadata",
                    metadata,
                    fetched_at=cached.fetched_at,
                    expires_at=cached.expires_at,
                )
            return metadata

        # Keep ADR safeguards local: failure returns neutral structural metadata;
        # no financial value is fabricated. A sourced ratio wins when available.
        metadata: dict[str, Any] = {
            "is_adr": False,
            "adr_ratio": None,
            "adr_ratio_source": None,
            "next_earnings_date": None,
        }
        try:
            profile, earnings = await asyncio.gather(
                self._get_json(client, f"{FMP_STABLE_BASE_URL}/sec-profile", {"symbol": ticker}),
                self._get_json(client, f"{FMP_STABLE_BASE_URL}/earnings", {"symbol": ticker}),
            )
            profile_row = profile[0] if isinstance(profile, list) and profile else {}
            if isinstance(profile_row, dict):
                metadata["is_adr"] = bool(profile_row.get("isAdr", False))
                ratio = profile_row.get("adrRatio")
                if ratio is not None and float(ratio) > 0:
                    metadata["adr_ratio"] = float(ratio)
                    metadata["adr_ratio_source"] = "fmp_sec_profile"
            next_date = _next_earnings_date(earnings, now.date())
            metadata["next_earnings_date"] = next_date.isoformat() if next_date else None
        except (httpx.HTTPError, TypeError, ValueError):
            # Existing defensive behavior: metadata failure must not destroy the
            # financial statement path or replace valid statement cache entries.
            metadata = _apply_adr_fallback(ticker, metadata)
            await self._cache_put(
                ticker,
                "company_metadata",
                metadata,
                fetched_at=now,
                expires_at=now + METADATA_TTL,
            )
            return metadata

        metadata = _apply_adr_fallback(ticker, metadata)

        await self._cache_put(
            ticker,
            "company_metadata",
            metadata,
            fetched_at=now,
            expires_at=now + METADATA_TTL,
        )
        return metadata

    async def _fetch_statement(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        statement_type: str,
        period: str,
        next_earnings: date | None,
    ) -> list[dict[str, Any]]:
        cache_key = f"{statement_type}:{period}"
        now = self._now()
        cached = await self._cache_get(ticker, cache_key, now=now)
        if cached is not None:
            return cached.payload if isinstance(cached.payload, list) else []

        endpoint = STATEMENT_ENDPOINTS[statement_type]
        payload = await self._get_json(
            client,
            f"{FMP_STABLE_BASE_URL}/{endpoint}",
            {"symbol": ticker, "period": period, "limit": 5},
        )
        if not isinstance(payload, list):
            raise ValueError(f"FMP {statement_type} returned a non-list payload")
        if not payload:
            raise ValueError(f"FMP {statement_type} returned no {period} reports")
        expires_at = now + statement_ttl(now, next_earnings)
        await self._cache_put(
            ticker,
            cache_key,
            payload,
            fetched_at=now,
            expires_at=expires_at,
        )
        return payload

    async def _fetch_analyst_estimates(
        self,
        client: httpx.AsyncClient,
        ticker: str,
    ) -> list[dict[str, Any]]:
        """Return validated annual consensus rows without inventing gaps."""
        cache_key = "analyst_estimates:annual"
        now = self._now()
        cached = await self._cache_get(ticker, cache_key, now=now)
        if cached is not None:
            return cached.payload if isinstance(cached.payload, list) else []

        payload = await self._get_json(
            client,
            f"{FMP_STABLE_BASE_URL}/analyst-estimates",
            {"symbol": ticker, "period": "annual", "page": 0, "limit": 10},
        )
        if not isinstance(payload, list):
            raise ValueError("FMP analyst estimates returned a non-list payload")

        rows: list[dict[str, Any]] = []
        for source in payload:
            if not isinstance(source, dict) or _parse_date(source.get("date")) is None:
                continue
            row = {key: source.get(key) for key in (
                "symbol", "date",
                "revenueLow", "revenueAvg", "revenueHigh",
                "ebitLow", "ebitAvg", "ebitHigh",
                "ebitdaLow", "ebitdaAvg", "ebitdaHigh",
                "netIncomeLow", "netIncomeAvg", "netIncomeHigh",
                "epsLow", "epsAvg", "epsHigh",
                "numAnalystsRevenue", "numAnalystsEps",
            )}
            try:
                revenue = [float(row[key]) for key in ("revenueLow", "revenueAvg", "revenueHigh")]
                ebit = [float(row[key]) for key in ("ebitLow", "ebitAvg", "ebitHigh")]
            except (TypeError, ValueError):
                continue
            if revenue[0] <= 0 or not (revenue[0] <= revenue[1] <= revenue[2]):
                continue
            if not (ebit[0] <= ebit[1] <= ebit[2]):
                continue
            row.update({
                "provider": "Financial Modeling Prep analyst estimates",
                "source_url": f"{FMP_STABLE_BASE_URL}/analyst-estimates",
                "fetched_at": now.isoformat(),
                "status": "provider_estimate",
            })
            rows.append(row)

        rows.sort(key=lambda item: item["date"])
        await self._cache_put(
            ticker,
            cache_key,
            rows,
            fetched_at=now,
            expires_at=now + ANALYST_ESTIMATES_TTL,
        )
        return rows

    async def fetch_financials(self, ticker: str) -> dict[str, Any]:
        normalized = ticker.strip().upper()
        self._cache_warnings.clear()
        if not self.api_key:
            return {"statements": {}, "metadata": {}, "warnings": ["FMP API key not configured"]}

        # Summary and valuation can execute in different event loops.  A
        # process-wide lock prevents both loops from refreshing the same
        # ticker simultaneously while keeping the event loop non-blocking.
        lock = _ticker_lock(normalized)
        while not lock.acquire(blocking=False):
            await asyncio.sleep(0.01)
        try:
            warnings: list[str] = []
            statements: dict[str, dict[str, list[dict[str, Any]]]] = {
                key: {"annual": [], "quarterly": []} for key in STATEMENT_ENDPOINTS
            }
            analyst_estimates: list[dict[str, Any]] = []
            async with httpx.AsyncClient() as client:
                metadata = await self._fetch_metadata(client, normalized)
                next_earnings = _parse_date(metadata.get("next_earnings_date"))
                tasks = {
                    (statement_type, period): asyncio.create_task(
                        self._fetch_statement(client, normalized, statement_type, period, next_earnings)
                    )
                    for statement_type in STATEMENT_ENDPOINTS
                    for period in ("annual", "quarter")
                }
                for (statement_type, period), task in tasks.items():
                    try:
                        statements[statement_type]["quarterly" if period == "quarter" else "annual"] = await task
                    except (httpx.HTTPError, TypeError, ValueError) as exc:
                        warnings.append(
                            f"FMP_{statement_type.upper()}_{period.upper()}_UNAVAILABLE: "
                            f"{type(exc).__name__}"
                        )
                try:
                    analyst_estimates = await self._fetch_analyst_estimates(client, normalized)
                except (httpx.HTTPError, TypeError, ValueError) as exc:
                    warnings.append(
                        f"FMP_ANALYST_ESTIMATES_UNAVAILABLE: {type(exc).__name__}"
                    )
            if analyst_estimates:
                # FMP analyst-estimates rows are denominated in the filer's
                # reporting currency (e.g. TWD for TSM), never converted to
                # USD. Stamp that currency here so downstream valuation code
                # can normalize before using these figures; do not assume USD.
                reported_currency = _reported_currency_from_statements(statements)
                for row in analyst_estimates:
                    row["reported_currency"] = reported_currency
            return {
                "statements": statements,
                "metadata": metadata,
                "analyst_estimates": analyst_estimates,
                "warnings": warnings,
            }
        finally:
            lock.release()
