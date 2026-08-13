"""Compact market snapshots for saved-stock and watchlist surfaces."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

import httpx

from app.core.config import get_settings
from app.models import (
    LiveQuoteResponse,
    SourceRecord,
    StockSnapshot,
    StockSnapshotsResponse,
)


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_NAMES_CACHE_TTL_SECONDS = 24 * 60 * 60
SNAPSHOT_QUOTE_WORKERS = 5


@dataclass(frozen=True)
class SecCompanyNames:
    names: dict[str, str]
    source: SourceRecord | None = None
    warnings: tuple[str, ...] = ()


_sec_cache_lock = Lock()
_sec_company_names_cache: tuple[float, SecCompanyNames] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ticker_aliases(ticker: str) -> set[str]:
    return {ticker, ticker.replace(".", "-"), ticker.replace("-", ".")}


def get_sec_company_names() -> SecCompanyNames:
    """Return the SEC ticker/title map, cached for 24 hours.

    A failed refresh is not cached. This lets a later request recover instead
    of treating an external outage as a valid mapping for a full day.
    """

    global _sec_company_names_cache

    with _sec_cache_lock:
        cached = _sec_company_names_cache
        if (
            cached is not None
            and monotonic() - cached[0] < SEC_COMPANY_NAMES_CACHE_TTL_SECONDS
        ):
            return cached[1]

        fetched_at = _utc_now()
        settings = get_settings()
        try:
            with httpx.Client(
                timeout=settings.provider_timeout_seconds,
                headers={"User-Agent": settings.sec_user_agent},
                follow_redirects=True,
            ) as client:
                response = client.get(SEC_TICKERS_URL)
                response.raise_for_status()
                payload = response.json()

            if not isinstance(payload, dict):
                raise ValueError("SEC ticker mapping response was not an object")

            names: dict[str, str] = {}
            for row in payload.values():
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                title = str(row.get("title") or "").strip()
                if not ticker or not title:
                    continue
                for alias in _ticker_aliases(ticker):
                    names.setdefault(alias, title)

            result = SecCompanyNames(
                names=names,
                source=SourceRecord(
                    provider="SEC Company Tickers",
                    source_url=SEC_TICKERS_URL,
                    source_timestamp=None,
                    fetched_at=fetched_at,
                ),
            )
            _sec_company_names_cache = (monotonic(), result)
            return result
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            return SecCompanyNames(
                names={},
                warnings=(
                    "SEC company-name mapping unavailable: "
                    f"{exc.__class__.__name__}.",
                ),
            )


def _snapshot_from_quote(
    ticker: str,
    quote_loader: Callable[[str], LiveQuoteResponse],
    company_names: SecCompanyNames,
) -> StockSnapshot:
    company_name = company_names.names.get(ticker)
    warnings = list(company_names.warnings)

    if company_name is None and not company_names.warnings:
        warnings.append(f"SEC company name unavailable for {ticker}.")

    try:
        quote = quote_loader(ticker)
    except Exception as exc:  # Provider failures degrade only this ticker.
        warnings.append(f"Quote unavailable for {ticker}: {exc.__class__.__name__}.")
        sources = (
            [company_names.source]
            if company_name and company_names.source
            else []
        )
        return StockSnapshot(
            ticker=ticker,
            company_name=company_name,
            status="unavailable",
            as_of=None,
            sources=sources,
            warnings=warnings,
        )

    sources = list(quote.sources)
    if company_name and company_names.source:
        sources.append(company_names.source)

    price_available = quote.data.price is not None
    if not price_available:
        status = "unavailable"
    elif quote.status != "success" or company_name is None:
        status = "partial"
    else:
        status = "success"

    return StockSnapshot(
        ticker=ticker,
        company_name=company_name,
        price=quote.data.price,
        change=quote.data.change,
        change_percent=quote.data.change_percent,
        currency=quote.data.currency,
        status=status,
        as_of=quote.as_of,
        sources=sources,
        warnings=[*warnings, *quote.warnings],
    )


def build_market_snapshots(
    tickers: list[str],
    quote_loader: Callable[[str], LiveQuoteResponse],
    *,
    concurrent: bool = True,
) -> StockSnapshotsResponse:
    """Compose ordered ticker snapshots without cross-ticker failure coupling."""

    company_names = get_sec_company_names()
    worker_count = min(SNAPSHOT_QUOTE_WORKERS, len(tickers))
    if not concurrent or worker_count <= 1:
        snapshots = [
            _snapshot_from_quote(ticker, quote_loader, company_names)
            for ticker in tickers
        ]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            snapshots = list(
                executor.map(
                    lambda ticker: _snapshot_from_quote(
                        ticker,
                        quote_loader,
                        company_names,
                    ),
                    tickers,
                )
            )

    statuses = {snapshot.status for snapshot in snapshots}
    if statuses == {"success"}:
        status = "success"
    elif statuses == {"unavailable"}:
        status = "unavailable"
    else:
        status = "partial"

    return StockSnapshotsResponse(
        status=status,
        as_of=_utc_now(),
        data=snapshots,
        warnings=list(company_names.warnings),
    )
