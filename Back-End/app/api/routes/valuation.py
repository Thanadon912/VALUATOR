from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
import logging
import math
import os
import json
from statistics import median
from fastapi import APIRouter, HTTPException, Query
from fastapi.params import Param
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Annotated, Dict, Any, Optional
import httpx
from app.core.config import get_settings
from app.core.performance_cache import (
    is_performance_cache_only,
    raise_performance_cache_miss,
)
from app.api.routes.sector_router import (
    ValuationMethodology,
    get_valuation_methodology,
)
from app.models import (
    ValuationInputsResponse,
    ValuationMethodologyResponse,
    ValuationResponse,
)
from app.providers.finnhub_metrics import FinnhubMetricProvider, fetch_peer_metrics
from app.providers.finnhub_profile import FinnhubProfileProvider
from app.providers.nasdaq import NasdaqMarketProvider
from app.providers.alpha_vantage import AlphaVantageOverviewProvider
from app.providers.yahoo import get_yahoo_quote, get_yahoo_quote_summary_metrics
from app.services.telemetry import (
    calculate_cost_of_equity,
    fetch_treasury_risk_free_rate_sync,
    get_risk_free_rate_metadata,
)
from app.services.international import country_risk_premium, derive_adr_ratio, fetch_usd_fx_rate

from app.services.valuation_engines import (
    calculate_implied_expectations,
    calculate_asset_based_valuation,
    calculate_capitalized_rnd,
    calculate_dcf_valuation,
    calculate_ddm_valuation,
    calculate_fcfe,
    calculate_growth_multistage_dcf,
    calculate_normalized_median_dcf,
    calculate_relative_valuation,
    calculate_standard_driver_dcf,
    calculate_residual_income_valuation,
    run_monte_carlo_simulation,
    normalize_equity_value_per_traded_share,
)
from app.providers.unified_financials import get_unified_financials_sync
from app.services.summary import _get_mrq, _get_ttm, _latest, _sum_required_values
from app.services.company_intelligence import (
    get_cached_company_classification,
    get_company_classification,
)
from app.services.sotp_configs import get_sotp_config

INPUT_FETCH_TIMEOUT_SECONDS = 60
# Never outlive shortest earnings-window statement TTL.
VALUATION_INPUT_CACHE_TTL_SECONDS = 12 * 60 * 60
VALUATION_TELEMETRY_CACHE_TTL_SECONDS = 6 * 60 * 60
RELATIVE_PEER_CACHE_TTL_SECONDS = 6 * 60 * 60
MARKET_RISK_PREMIUM = 0.055
MAX_EFFECTIVE_TAX_RATE = 0.25
MAX_STAGE_1_GROWTH_RATE = 0.20
MIN_STAGE_1_GROWTH_RATE = -0.05
MAX_REINVESTMENT_RATE = 0.35
NEGATIVE_FCF_NORMALIZATION_MARGIN = 0.03

_valuation_input_cache_lock = Lock()
_valuation_input_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_valuation_input_fetch_locks: dict[str, Lock] = {}
_valuation_telemetry_cache_lock = Lock()
_valuation_telemetry_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_valuation_telemetry_fetch_locks: dict[str, Lock] = {}
_relative_peer_cache_lock = Lock()
_relative_peer_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_relative_peer_fetch_locks: dict[str, Lock] = {}
_relative_metric_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_relative_metric_fetch_locks: dict[str, Lock] = {}
logger = logging.getLogger(__name__)

# Resilient, auditable fallback for the portfolio's supported large-cap names.
# Dynamic SEC/FMP/Gemini classification remains the primary selector. These
# candidates are used only when upstream classification cannot return peers.
CURATED_RELATIVE_PEERS: dict[str, tuple[tuple[str, str], ...]] = {
    "AAPL": (("MSFT", "MSFT"), ("GOOGL", "GOOGL"), ("DELL", "DELL"), ("HPQ", "HPQ")),
    "AMZN": (("WMT", "WMT"), ("EBAY", "EBAY"), ("MSFT", "MSFT"), ("GOOGL", "GOOGL")),
    "GM": (("F", "F"), ("TM", "TM"), ("STLA", "STLA"), ("TSLA", "TSLA")),
    "JPM": (("BAC", "BAC"), ("C", "C"), ("WFC", "WFC"), ("GS", "GS")),
    "MSFT": (("GOOGL", "GOOGL"), ("ORCL", "ORCL"), ("CRM", "CRM"), ("AMZN", "AMZN")),
    "NVDA": (("AMD", "AMD"), ("AVGO", "AVGO"), ("INTC", "INTC"), ("TSM", "TSM")),
    "TSLA": (("GM", "GM"), ("F", "F"), ("RIVN", "RIVN"), ("BYD", "1211.HK")),
    "TSM": (("INTC", "INTC"), ("TXN", "TXN"), ("ASML", "ASML"), ("NVDA", "NVDA")),
}


def _fetch_lock_for_ticker(ticker: str) -> Lock:
    with _valuation_input_cache_lock:
        lock = _valuation_input_fetch_locks.get(ticker)
        if lock is None:
            lock = Lock()
            _valuation_input_fetch_locks[ticker] = lock
        return lock


def _fetch_lock_for_telemetry(ticker: str) -> Lock:
    with _valuation_telemetry_cache_lock:
        lock = _valuation_telemetry_fetch_locks.get(ticker)
        if lock is None:
            lock = Lock()
            _valuation_telemetry_fetch_locks[ticker] = lock
        return lock


def _relative_fetch_lock(key: str, *, metric: bool = False) -> Lock:
    with _relative_peer_cache_lock:
        locks = _relative_metric_fetch_locks if metric else _relative_peer_fetch_locks
        return locks.setdefault(key, Lock())


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_float(value: Any) -> Optional[float]:
    parsed = _to_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def _cell_value(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        return _to_float(value.get("value"))
    return _to_float(value)


def _normalize_rnd_history_to_usd(
    history: list[dict[str, Any]],
    reported_currency: str | None,
    fx: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize every annual R&D observation under one auditable unit contract."""
    normalized: list[dict[str, Any]] = []
    source_units: set[str] = set()
    for source in history:
        item = dict(source)
        value = _to_float(item.get("value"))
        current_unit = str(item.get("unit") or "").upper()
        source_unit = str(item.get("reported_unit") or current_unit).upper()
        if value is None or value < 0 or not source_unit:
            return [], {"status": "unavailable", "reason": "invalid R&D observation"}
        source_units.add(source_unit)
        if current_unit == "USD":
            rate = 1.0
            rate_source = item.get("fx_rate_source") or "SEC USD presentation unit"
        elif reported_currency and source_unit == reported_currency.upper() and fx:
            rate = _positive_float(fx.get("rate"))
            rate_source = fx.get("source")
            if rate is None:
                return [], {"status": "unavailable", "reason": "invalid FX rate for R&D history"}
        else:
            return [], {
                "status": "unavailable",
                "reason": "R&D unit does not match the filing currency or USD",
                "source_unit": source_unit,
                "reported_currency": reported_currency,
            }
        item.update({
            "value": value * rate,
            "reported_unit": source_unit,
            "unit": "USD",
            "currency": "USD",
            "fx_rate": rate,
            "fx_rate_source": rate_source,
            "normalization_basis": "reported R&D amount * source_currency_USD_rate",
        })
        normalized.append(item)
    return normalized, {
        "status": "normalized" if normalized else "unavailable",
        "source_units": sorted(source_units),
        "output_unit": "USD" if normalized else None,
        "observation_count": len(normalized),
    }


_ANALYST_ESTIMATE_MONETARY_KEYS = (
    "revenueLow", "revenueAvg", "revenueHigh",
    "ebitLow", "ebitAvg", "ebitHigh",
    "ebitdaLow", "ebitdaAvg", "ebitdaHigh",
    "netIncomeLow", "netIncomeAvg", "netIncomeHigh",
)


def _normalize_analyst_estimates_to_usd(
    estimates: list[dict[str, Any]],
    reported_currency: str | None,
    fx: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize FMP consensus revenue/EBIT/EBITDA/net-income rows to USD.

    FMP's analyst-estimates endpoint returns consensus figures in the filer's
    own reporting currency (e.g. TWD for TSM), never converted to USD.
    Feeding these directly into a USD-denominated DCF silently inflates fair
    value by the FX magnitude. EPS and analyst-count fields are left as-is
    since they are not consumed as absolute USD amounts downstream.
    """
    normalized: list[dict[str, Any]] = []
    source_units: set[str] = set()
    for source in estimates:
        item = dict(source)
        row_currency = str(item.get("reported_currency") or "").upper()
        if not row_currency:
            return [], {
                "status": "unavailable",
                "reason": "analyst estimate row is missing a reported currency",
            }
        source_units.add(row_currency)
        if row_currency == "USD":
            rate, rate_source = 1.0, "identity conversion"
        elif reported_currency and row_currency == reported_currency.upper() and fx:
            rate = _positive_float(fx.get("rate"))
            rate_source = fx.get("source")
            if rate is None:
                return [], {"status": "unavailable", "reason": "invalid FX rate for analyst estimates"}
        else:
            row_fx = fetch_usd_fx_rate(row_currency)
            if row_fx is None:
                return [], {
                    "status": "unavailable",
                    "reason": "no FX rate available to normalize analyst estimates to USD",
                    "source_unit": row_currency,
                }
            rate = row_fx["rate"]
            rate_source = row_fx["source"]
        for key in _ANALYST_ESTIMATE_MONETARY_KEYS:
            value = _to_float(item.get(key))
            if value is not None:
                item[key] = value * rate
        item.update({
            "reported_currency": row_currency,
            "unit": "USD",
            "fx_rate": rate,
            "fx_rate_source": rate_source,
            "normalization_basis": "reported consensus amount * source_currency_USD_rate",
        })
        normalized.append(item)
    return normalized, {
        "status": "normalized" if normalized else "unavailable",
        "source_units": sorted(source_units),
        "output_unit": "USD" if normalized else None,
        "observation_count": len(normalized),
    }


def _normalize_financial_payloads_to_usd(*payloads: Any) -> dict[str, Any]:
    """Translate each monetary XBRL cell by its own unit before calculations."""
    conversions: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        unit = node.get("unit")
        value = _to_float(node.get("value"))
        if isinstance(unit, str):
            if unit.startswith("iso4217:"):
                clean_unit = unit.split(":")[1]
            else:
                clean_unit = unit
                
            is_currency = (
                len(clean_unit) == 3
                and clean_unit.isalpha() and clean_unit.isupper()
            )
            is_per_share = (
                clean_unit.endswith("/shares")
                and len(clean_unit.split("/")[0]) == 3
                and clean_unit.split("/")[0].isalpha()
                and clean_unit.split("/")[0].isupper()
            )
            
            if value is not None and (is_currency or is_per_share):
                currency_code = clean_unit.split("/")[0] if is_per_share else clean_unit
                if currency_code == "USD":
                    fx = fetch_usd_fx_rate("USD")
                else:
                    fx = conversions.get(currency_code) or fetch_usd_fx_rate(currency_code)
                if fx is None:
                    errors.append({"unit": unit, "reason": "USD FX rate unavailable"})
                else:
                    conversions[currency_code] = fx
                    target_unit = "USD/shares" if is_per_share else "USD"
                    node.update({
                        "value": value * float(fx["rate"]),
                        "reported_unit": unit,
                        "unit": target_unit,
                        "currency": "USD",
                        "fx_rate": float(fx["rate"]),
                        "fx_rate_source": fx["source"],
                        "fx_rate_as_of": fx.get("as_of"),
                        "currency_normalization_basis": f"reported value * source_currency_USD_rate",
                    })
        for child in node.values():
            if isinstance(child, (dict, list)):
                visit(child)

    for payload in payloads:
        visit(payload)
    return {
        "valuation_currency": "USD",
        "conversions": list(conversions.values()),
        "errors": errors,
        "status": "unavailable" if errors else "normalized",
    }


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(value, ceiling))


def _latest_annual_cell(financials: dict, stmt: str, row_id: str) -> Optional[dict[str, Any]]:
    stmt_data = financials.get("annual", {}).get(stmt, {})
    rows = stmt_data.get("rows", [])
    row = next((r for r in rows if r.get("id") == row_id), None)
    if not row:
        return None
    cells = row.get("cells", {})
    valid_dates = [key for key, cell in cells.items() if cell.get("value") is not None]
    if not valid_dates:
        return None
    valid_dates.sort()
    return cells[valid_dates[-1]]


def _latest_direct_filing_cell(
    financials: dict,
    stmt: str,
    row_id: str,
) -> Optional[dict[str, Any]]:
    """Return the latest direct-filing fact, excluding vendor-normalized cells."""
    candidates: list[dict[str, Any]] = []
    for period_name in ("quarterly", "annual"):
        stmt_data = financials.get(period_name, {}).get(stmt, {})
        row = next(
            (item for item in stmt_data.get("rows", []) if item.get("id") == row_id),
            None,
        )
        if not row:
            continue
        for cell in row.get("cells", {}).values():
            if _cell_value(cell) is None:
                continue
            if str(cell.get("taxonomy") or "").upper() == "FMP":
                continue
            candidates.append(cell)

    if not candidates:
        return None
    return max(
        candidates,
        key=lambda cell: (
            str(cell.get("period_end") or ""),
            str(cell.get("filed") or ""),
        ),
    )


def _latest_reliable_vendor_asset_cell(
    financials: dict,
    row_id: str,
) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[str]]:
    """Select a sourced vendor asset deduction without trusting a one-period zero gap.

    FMP sometimes publishes a newly opened period with zero for goodwill or
    intangible assets before those fields are populated. When the immediately
    preceding reported period is positive, retain that prior observation and
    expose the rejected period so callers can report the fallback explicitly.
    Two consecutive zero periods remain a reported zero rather than being
    inferred away.
    """
    candidates: list[tuple[str, int, dict[str, Any]]] = []
    for cadence_rank, period_name in enumerate(("annual", "quarterly")):
        rows = (
            financials.get(period_name, {})
            .get("balance_sheet", {})
            .get("rows", [])
        )
        row = next((item for item in rows if item.get("id") == row_id), None)
        if not row:
            continue
        for key, cell in row.get("cells", {}).items():
            value = _cell_value(cell)
            if value is None or value < 0:
                continue
            if str(cell.get("taxonomy") or "").upper() != "FMP":
                continue
            period_end = str(cell.get("period_end") or str(key)[-10:])
            if len(period_end) != 10 or period_end[4:5] != "-" or period_end[7:8] != "-":
                continue
            normalized_cell = dict(cell)
            normalized_cell["period_end"] = period_end
            candidates.append((period_end, cadence_rank, normalized_cell))

    if not candidates:
        return None, None, None

    candidates.sort(key=lambda item: (item[0], item[1]))
    latest_period, _, latest_cell = candidates[-1]
    if _cell_value(latest_cell) != 0:
        return latest_cell, "latest_vendor_statement", None

    prior_periods = sorted({period for period, _, _ in candidates if period < latest_period})
    if not prior_periods:
        return latest_cell, "latest_vendor_statement", None

    prior_period = prior_periods[-1]
    prior_candidates = [item for item in candidates if item[0] == prior_period]
    _, _, prior_cell = prior_candidates[-1]
    if (_cell_value(prior_cell) or 0) > 0:
        return (
            prior_cell,
            "prior_vendor_statement_after_unconfirmed_zero",
            latest_period,
        )
    return latest_cell, "latest_vendor_statement", None


def _annual_row_series(financials: dict, stmt: str, row_id: str) -> list[tuple[str, float]]:
    stmt_data = financials.get("annual", {}).get(stmt, {})
    rows = stmt_data.get("rows", [])
    row = next((r for r in rows if r.get("id") == row_id), None)
    if not row:
        return []
    series: list[tuple[str, float]] = []
    for key, cell in row.get("cells", {}).items():
        value = _cell_value(cell)
        if value is not None:
            series.append((key, value))
    return sorted(series, key=lambda item: item[0])


def _provider_annual_series(series: list[dict[str, Any]]) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for row in series:
        period = row.get("end") or row.get("period")
        value = _cell_value(row)
        if period and value is not None:
            values.append((str(period), value))
    return sorted(values, key=lambda item: item[0])


def _revenue_cagr(series: list[tuple[str, float]]) -> tuple[Optional[float], Optional[int]]:
    if len(series) < 2:
        return None, None
    years = min(3, len(series) - 1)
    start = series[-years - 1][1]
    end = series[-1][1]
    if start <= 0 or end <= 0:
        return None, None
    raw_cagr = (end / start) ** (1 / years) - 1
    return _clamp(raw_cagr, MIN_STAGE_1_GROWTH_RATE, MAX_STAGE_1_GROWTH_RATE), years


def _latest_same_period_pair(
    left_series: list[dict[str, Any]],
    right_series: list[dict[str, Any]],
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    right_by_period = {
        (row.get("end") or row.get("period"), row.get("unit")): row
        for row in right_series
        if row.get("value") is not None
    }
    for left in reversed(left_series):
        period = left.get("end") or left.get("period")
        unit = left.get("unit")
        right = right_by_period.get((period, unit))
        if right is None:
            continue
        left_value = _cell_value(left)
        right_value = _cell_value(right)
        if left_value is not None and right_value is not None:
            return left_value, right_value, period
    return None, None, None


def _first_positive(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _positive_float(value)
        if parsed is not None:
            return parsed
    return None


def _first_beta(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _to_float(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _positive_multiple(value: Any) -> Optional[float]:
    parsed = _to_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def _divide_positive(numerator: Any, denominator: Any) -> Optional[float]:
    n = _positive_float(numerator)
    d = _positive_float(denominator)
    if n is None or d is None:
        return None
    return n / d


def _default_relative_peer_specs(ticker: str) -> list[dict[str, Any]]:
    normalized = ticker.upper()
    provider_candidates: list[Any] = []
    try:
        classification = get_company_classification(normalized)
    except Exception as exc:
        logger.warning(
            "Classification peer selection failed for %s: %s",
            normalized,
            type(exc).__name__,
        )
    else:
        provider_candidates = classification.competitors
        scored_competitors = [
            peer for peer in provider_candidates
            if peer.reason != "Fallback peer due to unavailable AI scoring"
        ]
        if scored_competitors:
            return [
                {
                    "symbol": peer.ticker,
                    "source_symbol": peer.ticker,
                    "name": peer.ticker,
                    "overlap_score": peer.overlap_score,
                    "reason": peer.reason,
                    "selection_source": "Dynamic SEC/FMP/Gemini classification",
                }
                for peer in scored_competitors
            ]

    curated_peers = CURATED_RELATIVE_PEERS.get(normalized, ())
    if curated_peers:
        return [
            {
                "symbol": symbol,
                "source_symbol": source_symbol,
                "name": symbol,
                "overlap_score": None,
                "reason": "Curated comparable used because dynamic peer providers were unavailable.",
                "selection_source": "Curated provider-outage fallback",
            }
            for symbol, source_symbol in curated_peers
        ]

    # FMP may still return real stock-peer candidates when the SEC/Gemini
    # business-tag scoring layer is unavailable. For tickers without an
    # approved curated set, retain those sourced candidates instead of
    # turning a partial provider result into an empty peer universe.
    if provider_candidates:
        return [
            {
                "symbol": peer.ticker,
                "source_symbol": peer.ticker,
                "name": peer.ticker,
                "overlap_score": None,
                "reason": "Provider peer candidate; business-overlap scoring was unavailable.",
                "selection_source": "FMP stock-peer fallback (AI scoring unavailable)",
            }
            for peer in provider_candidates
        ]

    return []


# A multiple beyond these bounds is never a real comparable for a relative
# valuation; it signals a provider unit/basis mismatch rather than a
# genuinely expensive company. Used both to reject Yahoo's raw values and to
# guard the SEC-derived fallback itself.
PLAUSIBLE_PB_MAX = 100.0
PLAUSIBLE_EV_EBITDA_MAX = 150.0


def _derive_us_peer_multiples(source_symbol: str, market_cap: Optional[float]) -> dict[str, Any]:
    if "." in source_symbol:
        return {}
    inputs = get_valuation_inputs(source_symbol)
    if not inputs:
        return {}
    net_income = inputs.get("net_income")
    book_value = inputs.get("bv_0")
    ebitda = inputs.get("target_ebitda")
    debt = inputs.get("total_debt")
    cash = inputs.get("cash")

    enterprise_value = None
    if market_cap is not None and debt is not None and cash is not None:
        enterprise_value = market_cap + debt - cash

    pb = _divide_positive(market_cap, book_value)
    if pb is not None and pb > PLAUSIBLE_PB_MAX:
        pb = None
    ev_ebitda = _divide_positive(enterprise_value, ebitda)
    if ev_ebitda is not None and ev_ebitda > PLAUSIBLE_EV_EBITDA_MAX:
        ev_ebitda = None

    return {
        "pe": _divide_positive(market_cap, net_income),
        "pb": pb,
        "ev_ebitda": ev_ebitda,
        "derived_enterprise_value": enterprise_value,
        "derived_ebitda": ebitda,
    }


def _finnhub_peer_fallback(source_symbol: str) -> dict[str, Any]:
    result = FinnhubMetricProvider().fetch(source_symbol)
    data = result.data or {}
    return {
        "pe": _positive_multiple(data.get("peExclExtraTTM") or data.get("peBasicExclExtraTTM")),
        "pb": _positive_multiple(data.get("pbAnnual") or data.get("pbQuarterly")),
        "ev_ebitda": _positive_multiple(
            data.get("enterpriseValueOverEBITDATTM")
            or data.get("evToEbitda")
        ),
        "warnings": result.warnings or [],
    }


def _load_relative_peer_metrics(source_symbol: str) -> dict[str, Any]:
    quote = get_yahoo_quote(source_symbol)
    summary = get_yahoo_quote_summary_metrics(source_symbol)
    market_cap = _positive_float(quote.get("marketCap"))
    price = _positive_float(quote.get("regularMarketPrice"))
    eps = _to_float(quote.get("epsTrailingTwelveMonths") or summary.get("trailingEps"))
    yahoo_values = {
        "pe": _positive_multiple(quote.get("trailingPE"))
        or _positive_multiple(summary.get("trailingPE"))
        or (price / eps if price is not None and eps is not None and eps > 0 else None),
        "pb": _positive_multiple(quote.get("priceToBook"))
        or _positive_multiple(summary.get("priceToBook")),
        "ev_ebitda": _positive_multiple(quote.get("enterpriseToEbitda"))
        or _positive_multiple(summary.get("enterpriseToEbitda")),
    }
    # Some providers (Yahoo, notably for foreign filers such as ASML) return a
    # book value or enterprise value computed against a mismatched share
    # basis, producing multiples off by one to two orders of magnitude. Treat
    # an implausible reading as missing rather than publish it, so the
    # fallback chain below (Finnhub, then SEC-derived) can supply a plausible
    # sourced value instead.
    rejected_provider_values: dict[str, str] = {}
    if yahoo_values["pb"] is not None and yahoo_values["pb"] > PLAUSIBLE_PB_MAX:
        rejected_provider_values["pb"] = "Yahoo quote/summary"
        yahoo_values["pb"] = None
    if yahoo_values["ev_ebitda"] is not None and yahoo_values["ev_ebitda"] > PLAUSIBLE_EV_EBITDA_MAX:
        rejected_provider_values["ev_ebitda"] = "Yahoo quote/summary"
        yahoo_values["ev_ebitda"] = None

    values = dict(yahoo_values)
    fallback: dict[str, Any] = {}
    derived: dict[str, Any] = {}
    if any(values[name] is None for name in values):
        fallback = _finnhub_peer_fallback(source_symbol)
        values = {name: values[name] or fallback.get(name) for name in values}
    if any(values[name] is None for name in values):
        derived = _derive_us_peer_multiples(source_symbol, market_cap)
        values = {name: values[name] or derived.get(name) for name in values}

    metric_sources: dict[str, str | None] = {}
    for name, value in values.items():
        if value is None:
            metric_sources[name] = None
        elif yahoo_values[name] is not None and abs(value - yahoo_values[name]) < 0.001:
            metric_sources[name] = "Yahoo quote/summary"
        elif fallback.get(name) is not None and abs(value - fallback[name]) < 0.001:
            metric_sources[name] = "Finnhub fallback"
        else:
            metric_sources[name] = "SEC-derived"
    result = {**values, "market_cap": market_cap, "metric_sources": metric_sources}
    if rejected_provider_values:
        result["rejected_provider_values"] = rejected_provider_values
    return result


def _relative_peer_metrics(source_symbol: str) -> dict[str, Any]:
    normalized = source_symbol.upper()
    with _relative_peer_cache_lock:
        cached = _relative_metric_cache.get(normalized)
        if cached and monotonic() - cached[0] < RELATIVE_PEER_CACHE_TTL_SECONDS:
            return cached[1]
    with _relative_fetch_lock(normalized, metric=True):
        with _relative_peer_cache_lock:
            cached = _relative_metric_cache.get(normalized)
            if cached and monotonic() - cached[0] < RELATIVE_PEER_CACHE_TTL_SECONDS:
                return cached[1]
        metrics = _load_relative_peer_metrics(normalized)
        # Cache completed lookups, including unavailable multiples, so an
        # outage does not cause every target ticker to retry the same peer.
        with _relative_peer_cache_lock:
            _relative_metric_cache[normalized] = (monotonic(), metrics)
        return metrics


def build_relative_peers(ticker: str) -> list[dict[str, Any]]:
    normalized = ticker.upper()
    cache_only = is_performance_cache_only()
    with _relative_peer_cache_lock:
        cached = _relative_peer_cache.get(normalized)
        if cached and (
            cache_only
            or (cached[1] and monotonic() - cached[0] < RELATIVE_PEER_CACHE_TTL_SECONDS)
        ):
            return cached[1]
    if cache_only:
        raise_performance_cache_miss("relative_peers", normalized)

    with _relative_fetch_lock(normalized):
        with _relative_peer_cache_lock:
            cached = _relative_peer_cache.get(normalized)
            if (
                cached
                and cached[1]
                and monotonic() - cached[0] < RELATIVE_PEER_CACHE_TTL_SECONDS
            ):
                return cached[1]
        peers: list[dict[str, Any]] = []
        for spec in _default_relative_peer_specs(normalized):
            metrics = _relative_peer_metrics(spec["source_symbol"])
            peers.append({
                **spec,
                **metrics,
                "selection_source": spec.get("selection_source", "Dynamic classification"),
                "metric_basis": "Yahoo quote/summary first, Finnhub fallback next, SEC-derived for US peers as last resort; non-positive multiples are not meaningful and are returned as null.",
            })
        with _relative_peer_cache_lock:
            _relative_peer_cache[normalized] = (monotonic(), peers)
        return peers


def get_valuation_telemetry(ticker: str) -> Dict[str, Any]:
    normalized = ticker.upper()
    cache_only = is_performance_cache_only()
    with _valuation_telemetry_cache_lock:
        cached = _valuation_telemetry_cache.get(normalized)
        if cached and (
            cache_only
            or monotonic() - cached[0] < VALUATION_TELEMETRY_CACHE_TTL_SECONDS
        ):
            return cached[1]
    if cache_only:
        raise_performance_cache_miss("valuation_telemetry", normalized)

    fetch_lock = _fetch_lock_for_telemetry(normalized)
    with fetch_lock:
        with _valuation_telemetry_cache_lock:
            cached = _valuation_telemetry_cache.get(normalized)
            if cached and monotonic() - cached[0] < VALUATION_TELEMETRY_CACHE_TTL_SECONDS:
                return cached[1]

        telemetry: Dict[str, Any] = {
            "market_risk_premium": MARKET_RISK_PREMIUM,
        }
        warnings: list[str] = []

        fetch_treasury_risk_free_rate_sync()
        risk_metadata = get_risk_free_rate_metadata()
        if risk_metadata.get("risk_free_rate_source") != "fallback_default":
            telemetry.update(risk_metadata)

        yahoo_quote = get_yahoo_quote(normalized)
        current_price = _first_positive(yahoo_quote.get("regularMarketPrice"))
        if current_price is not None:
            telemetry["current_price"] = current_price
            telemetry["current_price_source"] = "Yahoo Finance quote"
        market_cap = _first_positive(yahoo_quote.get("marketCap"))
        beta = _first_beta(yahoo_quote.get("beta"))
        if market_cap is not None:
            telemetry["market_cap"] = market_cap
            telemetry["market_cap_source"] = "Yahoo Finance quote"
        if beta is not None:
            telemetry["beta"] = beta
            telemetry["beta_source"] = "Yahoo Finance quote"

        if market_cap is None:
            market_result = NasdaqMarketProvider().fetch(normalized)
            overview = market_result.data.get("overview") if market_result and market_result.data else {}
            market_cap = _first_positive(overview.get("market_cap"))
            if market_cap is not None:
                telemetry["market_cap"] = market_cap
                telemetry["market_cap_source"] = overview.get("market_cap_basis") or "Nasdaq Summary"
            warnings.extend(market_result.warnings or [])

        if beta is None:
            finnhub_result = FinnhubMetricProvider().fetch(normalized)
            beta = _first_beta(
                finnhub_result.data.get("beta") if finnhub_result.data else None,
                finnhub_result.data.get("beta5Y") if finnhub_result.data else None,
            )
            if beta is not None:
                telemetry["beta"] = beta
                telemetry["beta_source"] = "Finnhub stock metrics"
            warnings.extend(finnhub_result.warnings or [])

        if market_cap is None or beta is None:
            av_result = AlphaVantageOverviewProvider().fetch(normalized)
            if av_result.data:
                if market_cap is None:
                    market_cap = _first_positive(av_result.data.get("market_cap"))
                    if market_cap is not None:
                        telemetry["market_cap"] = market_cap
                        telemetry["market_cap_source"] = "Alpha Vantage OVERVIEW"
                if beta is None:
                    beta = _first_beta(av_result.data.get("beta"))
                    if beta is not None:
                        telemetry["beta"] = beta
                        telemetry["beta_source"] = "Alpha Vantage OVERVIEW"
            warnings.extend(av_result.warnings or [])

        domicile = None
        profile_result = FinnhubProfileProvider(
            api_key=get_settings().finnhub_api_key
        ).fetch_structural_profile(normalized)
        if profile_result.data:
            domicile = ((profile_result.data.get("fields") or {}).get("country") or {}).get("value")
        crp = country_risk_premium(domicile)
        if domicile:
            telemetry["country_of_domicile"] = domicile
        if crp is not None:
            telemetry.update({
                "country_risk_premium": crp["country_risk_premium"],
                "country_risk_premium_source": crp["source"],
                "country_risk_premium_as_of": crp["source_timestamp"],
            })
        elif domicile:
            warnings.append(f"Country risk premium unavailable for domicile {domicile}.")

        risk_free_rate = telemetry.get("risk_free_rate")
        beta = telemetry.get("beta")
        if risk_free_rate is not None and beta is not None:
            telemetry["cost_of_equity"] = calculate_cost_of_equity(
                beta=beta,
                risk_free_rate=risk_free_rate,
                market_risk_premium=MARKET_RISK_PREMIUM,
                country_risk_premium=telemetry.get("country_risk_premium", 0.0),
            )
            telemetry["cost_of_equity_basis"] = "risk_free_rate + adjusted_beta * market_risk_premium + country_risk_premium"

        if warnings:
            telemetry["telemetry_warnings"] = warnings

        with _valuation_telemetry_cache_lock:
            _valuation_telemetry_cache[normalized] = (monotonic(), telemetry)
        return telemetry


def _fetch_unified_financials(ticker: str):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(get_unified_financials_sync, ticker)
    try:
        return future.result(timeout=INPUT_FETCH_TIMEOUT_SECONDS)
    except TimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError(
            f"Financial input provider timed out after {INPUT_FETCH_TIMEOUT_SECONDS}s."
        )
    finally:
        if future.done():
            executor.shutdown(wait=False, cancel_futures=True)


def get_valuation_inputs(ticker: str):
    normalized = ticker.upper()
    cache_only = is_performance_cache_only()
    with _valuation_input_cache_lock:
        cached = _valuation_input_cache.get(normalized)
        if cached and (
            cache_only
            or monotonic() - cached[0] < VALUATION_INPUT_CACHE_TTL_SECONDS
        ):
            return cached[1]
    if cache_only:
        raise_performance_cache_miss("valuation_inputs", normalized)

    fetch_lock = _fetch_lock_for_ticker(normalized)
    with fetch_lock:
        with _valuation_input_cache_lock:
            cached = _valuation_input_cache.get(normalized)
            if cached and monotonic() - cached[0] < VALUATION_INPUT_CACHE_TTL_SECONDS:
                return cached[1]

        return _load_valuation_inputs(normalized)


def _load_valuation_inputs(ticker: str):
    try:
        res = _fetch_unified_financials(ticker)
        if not res.data:
            return {}
        financials = deepcopy(res.data.get("financial_statements", {}))
        instants = deepcopy(res.data.get("instants", {}))
        annual = deepcopy(res.data.get("annual", {}))
        profile = res.data.get("profile", {})
        fmp_metadata = res.data.get("fmp_metadata", {})
        analyst_estimates = deepcopy(res.data.get("analyst_estimates") or [])
        revenue_mix = deepcopy(res.data.get("revenue_mix") or {})
        adaptive_valuation_data = deepcopy(res.data.get("adaptive_valuation_data") or {})
        currency_normalization = _normalize_financial_payloads_to_usd(
            financials, instants, annual, adaptive_valuation_data
        )
        sic_code = adaptive_valuation_data.get("sic_code") or profile.get("sic")
        
        fh_provider = FinnhubProfileProvider(api_key=get_settings().finnhub_api_key)
        fh_res = fh_provider.fetch_structural_profile(ticker)
        finnhub_industry = None
        country_of_domicile = None
        finnhub_currency = None
        if fh_res.data and "fields" in fh_res.data and "finnhub_industry" in fh_res.data["fields"]:
            finnhub_industry = fh_res.data["fields"]["finnhub_industry"].get("value")
        if fh_res.data and "fields" in fh_res.data:
            country_of_domicile = (fh_res.data["fields"].get("country") or {}).get("value")
            finnhub_currency = (fh_res.data["fields"].get("currency") or {}).get("value")
            
        valuation_methodology = get_valuation_methodology(sic_code, finnhub_industry=finnhub_industry)
        
        total_assets = _cell_value(_get_mrq(financials, "balance_sheet", "totalAssets")) or _cell_value(_get_mrq(financials, "balance_sheet", "total_assets"))
        total_liabilities = _cell_value(_get_mrq(financials, "balance_sheet", "totalLiabilities")) or _cell_value(_get_mrq(financials, "balance_sheet", "total_liabilities"))
        goodwill_filing_cell = _latest_direct_filing_cell(
            financials,
            "balance_sheet",
            "goodwill",
        )
        intangible_filing_cell = _latest_direct_filing_cell(
            financials,
            "balance_sheet",
            "intangible_assets",
        )
        goodwill_vendor_cell = None
        goodwill_vendor_basis = None
        goodwill_rejected_period = None
        goodwill = _cell_value(goodwill_filing_cell)
        if goodwill is None:
            (
                goodwill_vendor_cell,
                goodwill_vendor_basis,
                goodwill_rejected_period,
            ) = _latest_reliable_vendor_asset_cell(financials, "goodwill")
            goodwill = _cell_value(goodwill_vendor_cell)
        intangible_vendor_cell = None
        intangible_vendor_basis = None
        intangible_rejected_period = None
        intangible_assets = _cell_value(intangible_filing_cell)
        if intangible_assets is None:
            (
                intangible_vendor_cell,
                intangible_vendor_basis,
                intangible_rejected_period,
            ) = _latest_reliable_vendor_asset_cell(financials, "intangible_assets")
            intangible_assets = _cell_value(intangible_vendor_cell)

        asset_input_warnings = []
        if goodwill_rejected_period:
            asset_input_warnings.append({
                "code": "GOODWILL_VENDOR_ZERO_PLACEHOLDER_REJECTED",
                "rejected_period": goodwill_rejected_period,
                "selected_period": str(goodwill_vendor_cell.get("period_end") or "")
                if goodwill_vendor_cell
                else None,
            })
        if intangible_rejected_period:
            asset_input_warnings.append({
                "code": "INTANGIBLE_ASSETS_VENDOR_ZERO_PLACEHOLDER_REJECTED",
                "rejected_period": intangible_rejected_period,
                "selected_period": str(intangible_vendor_cell.get("period_end") or "")
                if intangible_vendor_cell
                else None,
            })
        
        shares = instants.get("shares", {})
        fmp_shares_cell = (
            _get_mrq(financials, "income", "shares_outstanding")
            or _get_mrq(financials, "income", "diluted_average_shares")
            or _get_mrq(financials, "income", "basic_average_shares")
        )
        weighted_average_shares = _cell_value(fmp_shares_cell)
        shares_outstanding = weighted_average_shares
        if shares_outstanding is None:
            shares_outstanding = _cell_value(_get_mrq(financials, "balance_sheet", "shares_outstanding"))
        if shares_outstanding is None:
            shares_outstanding = _cell_value(shares)
        traded_shares = _positive_float(get_yahoo_quote(ticker).get("sharesOutstanding"))
        if traded_shares is not None:
            shares_outstanding = traded_shares
        classification = get_company_classification(ticker)
        is_fpi = bool(fmp_metadata.get("is_adr", classification.is_adr))
        adr_ratio = _positive_float(fmp_metadata.get("adr_ratio")) or classification.adr_ratio
        
        adr_ratio_source = (
            fmp_metadata.get("adr_ratio_source")
            or ("dynamically fetched from FMP sec-profile" if is_fpi else "Default (1.0) for Domestic US Equity")
        )
            
        annual_cfo, annual_capex_raw, annual_fcf_period = _latest_same_period_pair(
            annual.get("operating_cash_flow", []),
            annual.get("capital_expenditure", []),
        )
        ttm_cfo = _cell_value(_get_ttm(financials, "cash_flow", "netCashFromOperatingActivities")) or _cell_value(_get_ttm(financials, "cash_flow", "operating_cash_flow"))
        ttm_capex_raw = _cell_value(_get_ttm(financials, "cash_flow", "capitalExpenditures")) or _cell_value(_get_ttm(financials, "cash_flow", "capital_expenditure"))
        cfo = annual_cfo if annual_cfo is not None else ttm_cfo
        capex_raw = annual_capex_raw if annual_capex_raw is not None else ttm_capex_raw
        capex = abs(capex_raw) if capex_raw is not None else None
        fcf_basis = (
            f"latest_annual_cash_flow:{annual_fcf_period}"
            if annual_cfo is not None and annual_capex_raw is not None
            else "ttm_cash_flow"
            if ttm_cfo is not None and ttm_capex_raw is not None
            else None
        )
        
        debt_current = _cell_value(instants.get("debt_current"))
        debt_noncurrent = _cell_value(instants.get("debt_noncurrent"))
        total_debt_mrq = _cell_value(_get_mrq(financials, "balance_sheet", "totalDebt")) or _cell_value(_get_mrq(financials, "balance_sheet", "total_debt"))
        total_debt = total_debt_mrq
        if total_debt is None and debt_current is not None and debt_noncurrent is not None:
            total_debt = debt_current + debt_noncurrent
        if total_debt is None:
            total_debt = _sum_required_values(instants.get("debt_current"), instants.get("debt_noncurrent"))
        
        cash_equivalents = _cell_value(_get_mrq(financials, "balance_sheet", "cash")) or _cell_value(_get_mrq(financials, "balance_sheet", "cashAndEquivalents"))
        short_term_investments = _cell_value(_get_mrq(financials, "balance_sheet", "marketable_securities_current")) or 0
        cash = cash_equivalents + short_term_investments if cash_equivalents is not None else None
        if cash is None:
            cash = _cell_value(instants.get("cash"))
        dividends_raw = _cell_value(_get_ttm(financials, "cash_flow", "dividendsPaid")) or _cell_value(_get_ttm(financials, "cash_flow", "dividends_paid"))
        dividends_paid = abs(dividends_raw) if dividends_raw is not None else None
        historical_dividends = [
            abs(value)
            for _, value in _annual_row_series(financials, "cash_flow", "dividends_paid")
            if value is not None
        ]
        
        net_income = _cell_value(_get_ttm(financials, "income_statement", "netIncome")) or _cell_value(_get_ttm(financials, "income", "net_income"))
        if net_income is None:
            net_income = _cell_value(_latest(annual.get("net_income", [])))
        bv_0_val = _cell_value(_get_mrq(financials, "balance_sheet", "totalEquity")) or _cell_value(_get_mrq(financials, "balance_sheet", "stockholders_equity"))
        if total_assets is None:
            total_assets = _cell_value(instants.get("assets"))
        if total_liabilities is None:
            total_liabilities = _cell_value(instants.get("liabilities"))
        if bv_0_val is None:
            bv_0_val = _cell_value(instants.get("equity"))
        total_liabilities_basis = "reported_total_liabilities"
        if total_liabilities is None and total_assets is not None and bv_0_val is not None:
            total_liabilities = total_assets - bv_0_val
            total_liabilities_basis = "derived_from_total_assets_minus_stockholders_equity"
        bv_0 = bv_0_val
        if bv_0 is None and total_assets is not None and total_liabilities is not None:
            bv_0 = total_assets - total_liabilities
        
        target_eps = net_income / shares_outstanding if net_income is not None and shares_outstanding else None
        target_bvps = bv_0 / shares_outstanding if bv_0 is not None and shares_outstanding else None
        
        annual_revenue_series = (
            _provider_annual_series(annual.get("revenue", []))
            or _annual_row_series(financials, "income", "total_revenue")
        )
        revenue_cagr, revenue_cagr_years = _revenue_cagr(annual_revenue_series)
        base_revenue = annual_revenue_series[-1][1] if annual_revenue_series else None
        base_fiscal_year = None
        if annual_revenue_series:
            try:
                base_fiscal_year = int(str(annual_revenue_series[-1][0])[:4])
            except ValueError:
                base_fiscal_year = None

        annual_operating_income = (
            _cell_value(_latest(annual.get("operating_income", [])))
            or _cell_value(_latest_annual_cell(financials, "income", "operating_income"))
        )
        if annual_operating_income is None:
            annual_operating_income = _cell_value(_get_ttm(financials, "income", "operating_income"))
        ebit_margin = (
            annual_operating_income / base_revenue
            if annual_operating_income is not None and base_revenue and base_revenue > 0
            else None
        )

        tax_prov = (
            _cell_value(_latest_annual_cell(financials, "income", "tax_provision"))
            or _cell_value(_get_ttm(financials, "income_statement", "provisionForIncomeTaxes"))
            or _cell_value(_get_ttm(financials, "income", "tax_provision"))
        )
        ebt = (
            _cell_value(_latest_annual_cell(financials, "income", "pretax_income"))
            or (
                net_income + tax_prov
                if net_income is not None and tax_prov is not None
                else None
            )
        )
        effective_tax_rate = None
        if tax_prov is not None and ebt is not None and ebt > 0:
            effective_tax_rate = _clamp(abs(tax_prov) / ebt, 0.0, MAX_EFFECTIVE_TAX_RATE)

        int_exp = (
            _cell_value(_latest_annual_cell(financials, "income", "interest_expense"))
            or _cell_value(_get_ttm(financials, "income_statement", "interestExpense"))
            or _cell_value(_get_ttm(financials, "income", "interest_expense"))
        )
        if int_exp is not None:
            int_exp = abs(int_exp)

        if annual_operating_income is None and net_income is not None and tax_prov is not None:
            annual_operating_income = net_income + abs(tax_prov) + (int_exp or 0.0)
            ebit_margin = (
                annual_operating_income / base_revenue
                if base_revenue and base_revenue > 0
                else None
            )

        dep_amort = (
            _cell_value(_latest_annual_cell(financials, "cash_flow", "depreciation_amortization"))
            or _cell_value(_get_ttm(financials, "cash_flow", "depreciation"))
            or _cell_value(_get_ttm(financials, "cash_flow", "depreciation_amortization"))
        )
        if dep_amort is None:
            dep_amort = _cell_value(_latest(annual.get("depreciation_amortization", [])))
        if dep_amort is not None:
            dep_amort = abs(dep_amort)

        fcf_0 = cfo - capex if cfo is not None and capex is not None else None
        maintenance_capex = min(capex, dep_amort) if capex is not None and dep_amort is not None else None
        maintenance_adjusted_fcf_0 = (
            cfo - maintenance_capex
            if cfo is not None and maintenance_capex is not None
            else fcf_0
        )
        change_in_wc_raw = (
            _cell_value(_latest_annual_cell(financials, "cash_flow", "change_in_working_capital"))
            or _cell_value(_get_ttm(financials, "cash_flow", "change_in_working_capital"))
        )
        change_in_nwc = -change_in_wc_raw if change_in_wc_raw is not None else 0.0

        nopat_base = (
            annual_operating_income * (1 - effective_tax_rate)
            if annual_operating_income is not None and effective_tax_rate is not None
            else None
        )
        reinvestment_rate = None
        latest_revenue_delta = None
        if len(annual_revenue_series) >= 2:
            latest_revenue_delta = annual_revenue_series[-1][1] - annual_revenue_series[-2][1]
        if capex is not None and dep_amort is not None and latest_revenue_delta is not None and latest_revenue_delta > 0:
            net_reinvestment = max(capex - dep_amort + change_in_nwc, 0)
            reinvestment_rate = _clamp(
                net_reinvestment / latest_revenue_delta,
                0.0,
                MAX_REINVESTMENT_RATE,
            )
        elif capex is not None and dep_amort is not None and nopat_base is not None and nopat_base > 0:
            net_reinvestment = max(capex - dep_amort + change_in_nwc, 0)
            reinvestment_rate = _clamp(net_reinvestment / nopat_base, 0.0, MAX_REINVESTMENT_RATE)

        stage_1_growth_rate_default = revenue_cagr
        if stage_1_growth_rate_default is None and fcf_0 is not None and base_revenue:
            stage_1_growth_rate_default = 0.0
        
        target_ebitda = None
        if net_income is not None and tax_prov is not None and int_exp is not None and dep_amort is not None:
            target_ebitda = net_income + abs(tax_prov) + abs(int_exp) + abs(dep_amort)
        if target_ebitda is None:
            operating_income = _cell_value(_get_ttm(financials, "income", "operating_income"))
            if operating_income is None:
                operating_income = _cell_value(_latest(annual.get("operating_income", [])))
            if operating_income is not None and dep_amort is not None:
                target_ebitda = operating_income + abs(dep_amort)
        
        operating_margin_history = adaptive_valuation_data.get(
            "operating_margin_history",
            [],
        )
        if not operating_margin_history and ebit_margin is not None:
            operating_margin_history = [
                {
                    "value": ebit_margin,
                    "unit": "ratio",
                    "basis": "derived_current_ebit_margin_from_net_income_tax_interest",
                }
            ]

        inputs = {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_liabilities_basis": total_liabilities_basis if total_liabilities is not None else None,
            "goodwill": goodwill,
            "goodwill_basis": (
                f"sec_company_facts:{goodwill_filing_cell.get('concept')}"
                if goodwill_filing_cell
                else goodwill_vendor_basis
            ),
            "goodwill_source_timestamp": (
                goodwill_filing_cell.get("period_end")
                if goodwill_filing_cell
                else goodwill_vendor_cell.get("period_end")
                if goodwill_vendor_cell
                else None
            ),
            "intangible_assets": intangible_assets,
            "intangible_assets_basis": (
                f"sec_company_facts:{intangible_filing_cell.get('concept')}"
                if intangible_filing_cell
                else intangible_vendor_basis
            ),
            "intangible_assets_source_timestamp": (
                intangible_filing_cell.get("period_end")
                if intangible_filing_cell
                else intangible_vendor_cell.get("period_end")
                if intangible_vendor_cell
                else None
            ),
            "asset_input_warnings": asset_input_warnings,
            "shares_outstanding": shares_outstanding,
            "adr_ratio": adr_ratio,
            "adr_ratio_source": adr_ratio_source,
            "is_foreign_private_issuer": is_fpi,
            "country_of_domicile": country_of_domicile,
            "shares_outstanding_basis": (
                "latest_yahoo_point_in_time_shares_outstanding"
                if traded_shares is not None
                else "latest_fmp_income_statement_weighted_average_shares"
                if weighted_average_shares is not None
                else shares.get("basis") if isinstance(shares, dict) else None
            ),
            "shares_outstanding_input_refs": (
                ["yahoo:sharesOutstanding"]
                if traded_shares is not None
                else ["fmp:income_statement:weightedAverageShsOutDil|weightedAverageShsOut"]
                if weighted_average_shares is not None
                else shares.get("input_refs", []) if isinstance(shares, dict) else []
            ),
            "weighted_average_shares": weighted_average_shares,
            "cfo": cfo,
            "capex": capex,
            "reported_fcf_0": fcf_0,
            "maintenance_capex": maintenance_capex,
            "fcf_0": maintenance_adjusted_fcf_0,
            "fcf_basis": fcf_basis,
            "change_in_nwc": change_in_nwc,
            "total_debt": total_debt,
            "cash": cash,
            "base_revenue": base_revenue,
            "base_fiscal_year": base_fiscal_year,
            "base_revenue_basis": (
                f"latest_annual_revenue:{annual_revenue_series[-1][0]}"
                if annual_revenue_series
                else None
            ),
            "revenue_cagr_3y": revenue_cagr,
            "revenue_cagr_years": revenue_cagr_years,
            "stage_1_growth_rate_default": stage_1_growth_rate_default,
            "operating_income": annual_operating_income,
            "ebit_margin": ebit_margin,
            "tax_provision": tax_prov,
            "ebt": ebt,
            "effective_tax_rate": effective_tax_rate,
            "interest_expense": int_exp,
            "depreciation_amortization": dep_amort,
            "reinvestment_rate": reinvestment_rate,
            "reinvestment_rate_basis": (
                "maintenance CapEx uses depreciation/amortization proxy; growth reinvestment is max(capex - depreciation_amortization + change_in_nwc, 0) / latest annual revenue delta, capped at 35%"
                if reinvestment_rate is not None
                else None
            ),
            "dividends_paid": dividends_paid,
            "historical_dividends": historical_dividends,
            "net_income": net_income,
            "bv_0": bv_0,
            "target_eps": target_eps,
            "target_bvps": target_bvps,
            "target_ebitda": target_ebitda,
            "sic_code": sic_code,
            "sic_description": (
                adaptive_valuation_data.get("sic_description")
                or profile.get("sic_description")
            ),
            "finnhub_industry": finnhub_industry,
            "valuation_methodology": valuation_methodology.value,
            "adaptive_valuation_data": adaptive_valuation_data,
            "r_and_d_history": adaptive_valuation_data.get("r_and_d_history", []),
            "regulatory_capital": adaptive_valuation_data.get(
                "regulatory_capital",
                {},
            ),
            "operating_margin_history": operating_margin_history,
            "operating_income_history": adaptive_valuation_data.get(
                "operating_income_history",
                [],
            ),
            "capex_history": adaptive_valuation_data.get("capex_history", []),
            "net_income_history": adaptive_valuation_data.get(
                "net_income_history",
                [],
            ),
            "analyst_estimates": analyst_estimates,
            "revenue_mix": revenue_mix,
        }
        reported_currency = profile.get("reported_currency") or financials.get("annual", {}).get("income", {}).get("currency") or finnhub_currency
        inputs["reported_currency"] = reported_currency
        inputs["valuation_currency"] = "USD"
        fx = fetch_usd_fx_rate(reported_currency) if reported_currency else None
        inputs["fx_translation"] = fx
        inputs["currency_normalization"] = currency_normalization
        if currency_normalization["errors"]:
            inputs["fx_translation_unavailable"] = True
        normalized_rnd, rnd_normalization = _normalize_rnd_history_to_usd(
            inputs.get("r_and_d_history", []), reported_currency, fx
        )
        if normalized_rnd and inputs.get("base_revenue") is not None:
            if any(item["value"] > inputs["base_revenue"] for item in normalized_rnd[-3:]):
                normalized_rnd = []
                rnd_normalization = {
                    **rnd_normalization,
                    "status": "unavailable",
                    "reason": "R&D exceeds revenue after normalization; unit magnitude is not comparable",
                }
        inputs["r_and_d_history"] = normalized_rnd
        inputs["r_and_d_history_normalization"] = rnd_normalization

        normalized_estimates, estimates_normalization = _normalize_analyst_estimates_to_usd(
            inputs.get("analyst_estimates", []), reported_currency, fx
        )
        if normalized_estimates and inputs.get("base_revenue"):
            # FMP's analyst-estimates rows include trailing actuals alongside
            # forward consensus. Only the first *forward-looking* year (after
            # base_fiscal_year, matching the filter calculate_growth_multistage_dcf
            # and _consensus_anchor_growth already apply) should be within a
            # plausible band of the trailing base revenue. A larger gap means
            # the FX normalization basis was wrong (e.g. mismatched reporting
            # currency) rather than a genuine growth forecast; do not let a
            # scale error masquerade as consensus.
            base_fiscal_year = inputs.get("base_fiscal_year")
            forward_years: list[tuple[int, float]] = []
            for row in normalized_estimates:
                try:
                    year = int(str(row.get("date"))[:4])
                except (TypeError, ValueError):
                    continue
                revenue = _to_float(row.get("revenueAvg"))
                if revenue is None or revenue <= 0:
                    continue
                if base_fiscal_year is not None and year <= base_fiscal_year:
                    continue
                forward_years.append((year, revenue))
            first_year_revenue = min((revenue for _, revenue in forward_years), default=None)
            if first_year_revenue is not None and not (
                0.2 * inputs["base_revenue"] <= first_year_revenue <= 5.0 * inputs["base_revenue"]
            ):
                normalized_estimates = []
                estimates_normalization = {
                    **estimates_normalization,
                    "status": "unavailable",
                    "reason": "normalized consensus revenue is not within a plausible range of base revenue; falling back to filing-derived forecast",
                }
        inputs["analyst_estimates"] = normalized_estimates
        inputs["analyst_estimates_normalization"] = estimates_normalization
        if any(value is not None for value in inputs.values()):
            with _valuation_input_cache_lock:
                _valuation_input_cache[ticker.upper()] = (monotonic(), inputs)
        return inputs
    except Exception:
        logger.exception("Error fetching valuation inputs for %s", ticker)
        return {}

router = APIRouter(prefix="/api/v1/valuation", tags=["valuation"])

def format_response(
    ticker: str,
    computed_fair_value: Optional[float],
    status: str,
    assumptions: Dict[str, Any],
    current_price: Optional[float] = None,
    valuation_methodology: Optional[str] = None,
    engine_metadata: Optional[Dict[str, Any]] = None,
    projections: Optional[list[dict[str, Any]]] = None,
    monte_carlo_results: Optional[Dict[str, float]] = None,
    implied_expectations: Optional[Dict[str, Any]] = None,
    sotp_breakdown: Optional[Dict[str, Any]] = None,
    forward_dcf: Optional[Dict[str, Any]] = None,
    reverse_dcf_sotp: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    telemetry = get_valuation_telemetry(ticker)
    selected_methodology = (
        valuation_methodology
        or assumptions.get("valuation_methodology")
        or assumptions.get("methodology")
        or assumptions.get("engine")
        or "Unknown"
    )
    selected_engine_metadata = (
        engine_metadata
        if engine_metadata is not None
        else assumptions.get("engine_metadata") or {}
    )
    selected_projections = (
        projections
        if projections is not None
        else assumptions.get("projections") or []
    )
    enriched_assumptions = {
        **assumptions,
        "valuation_methodology": selected_methodology,
        "engine_metadata": selected_engine_metadata,
        "projections": selected_projections,
        "telemetry": telemetry,
    }
    for key in (
        "market_cap",
        "market_cap_source",
        "beta",
        "beta_source",
        "risk_free_rate",
        "risk_free_rate_source",
        "risk_free_rate_as_of",
        "market_risk_premium",
        "cost_of_equity",
        "cost_of_equity_basis",
        "country_of_domicile",
        "country_risk_premium",
        "country_risk_premium_source",
        "country_risk_premium_as_of",
        "current_price",
        "current_price_source",
    ):
        if key in telemetry and key not in enriched_assumptions:
            enriched_assumptions[key] = telemetry[key]

    selected_current_price = current_price
    if selected_current_price is None:
        selected_current_price = telemetry.get("current_price")

    mos = 0.0
    if computed_fair_value and computed_fair_value > 0 and selected_current_price is not None and selected_current_price > 0:
        mos = ((computed_fair_value - selected_current_price) / selected_current_price) * 100.0
        
    payload = {
        "ticker": ticker.upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_price": selected_current_price,
        "computed_fair_value": computed_fair_value,
        "valuation_status": status,
        "margin_of_safety_percentage": mos,
        "valuation_methodology": selected_methodology,
        "engine_metadata": selected_engine_metadata,
        "projections": selected_projections,
        "monte_carlo_results": monte_carlo_results or assumptions.get("monte_carlo_results") or {},
        "implied_expectations": implied_expectations or assumptions.get("implied_expectations") or {},
        "underlying_assumptions": enriched_assumptions,
        "sotp_breakdown": sotp_breakdown or assumptions.get("sotp_breakdown"),
        "forward_dcf": forward_dcf,
        "reverse_dcf_sotp": reverse_dcf_sotp,
    }

    # Normalize exactly once. Most valuation engines already return ADR-adjusted
    # values; raw-per-ordinary-share engines delegate adjustment to this boundary.
    adr = assumptions.get("adr_ratio") or 1.0
    adr_already_applied = bool(assumptions.get("adr_ratio_applied"))
    if adr != 1.0 and not adr_already_applied:
        # Note: We do NOT scale computed_fair_value, target_eps, or shares_outstanding here.
        # Data providers (like Finnhub/Yahoo) generally report shares_outstanding as the number
        # of traded ADRs (e.g. TSM shares outstanding is 5.18B ADRs, not 25.9B common shares).
        # Thus, net_income / shares_outstanding is already the EPS per ADR, and total equity / shares
        # is already the value per ADR.
        # Recalculate Margin of Safety if root value changed
        if payload.get("computed_fair_value") and payload["computed_fair_value"] > 0 and selected_current_price and selected_current_price > 0:
            payload["margin_of_safety_percentage"] = ((payload["computed_fair_value"] - selected_current_price) / selected_current_price) * 100.0

    return payload


def missing_input_response(
    ticker: str,
    engine: str,
    missing_inputs: list[str],
    available_inputs: Dict[str, Any],
    valuation_methodology: Optional[str] = None,
    engine_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return format_response(
        ticker,
        None,
        "MISSING_INPUT",
        {
            "engine": engine,
            "missing_inputs": missing_inputs,
            "available_inputs": {
                key: value for key, value in available_inputs.items() if value is not None
            },
            "calculation_basis": "Not calculated because required sourced inputs are missing.",
        },
        valuation_methodology=valuation_methodology,
        engine_metadata=engine_metadata,
    )


def unavailable_output_response(
    ticker: str,
    engine: str,
    reason_code: str,
    reason: str,
    assumptions: Dict[str, Any],
    valuation_methodology: Optional[str] = None,
    engine_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return an unavailable state when an engine produces an unusable result.

    Inputs were present and valid, but the model output cannot be published as a
    fair value (e.g. a non-positive equity value). AGENTS.md forbids presenting
    such a figure as a real value, so surface the reason instead of the number.
    """
    return format_response(
        ticker,
        None,
        "UNAVAILABLE",
        {
            **assumptions,
            "engine": engine,
            "unavailable_reason_code": reason_code,
            "unavailable_reason": reason,
            "calculation_basis": (
                "Model completed but produced a value that cannot be published as a fair value."
            ),
        },
        valuation_methodology=valuation_methodology,
        engine_metadata=engine_metadata,
    )


def invalid_input_response(
    ticker: str,
    engine: str,
    error: Exception,
    valuation_methodology: Optional[str] = None,
) -> Dict[str, Any]:
    if isinstance(error, HTTPException):
        raise error
    logger.warning(
        "valuation_input_rejected",
        extra={"ticker": ticker.upper(), "engine": engine, "error_type": type(error).__name__},
    )
    return format_response(
        ticker,
        None,
        "INVALID_INPUT",
        {
            "engine": engine,
            "error_code": "VALUATION_INPUT_INVALID",
            "error": "One or more valuation inputs are invalid.",
            "calculation_basis": "Not calculated because one or more inputs failed validation.",
        },
        valuation_methodology=valuation_methodology,
    )


def missing_required(values: Dict[str, Any], required: list[str]) -> list[str]:
    return [key for key in required if values.get(key) is None]


def reject_non_finite_query_values(**values: float | None) -> None:
    invalid = [
        name
        for name, value in values.items()
        if value is not None and not math.isfinite(value)
    ]
    if invalid:
        raise ValueError("Non-finite numeric inputs are not allowed.")


def _series_numeric_values(series: Any) -> list[float]:
    if not isinstance(series, list):
        return []
    values: list[float] = []
    for row in series:
        value = _cell_value(row)
        if value is not None:
            values.append(value)
    return values


def _latest_series_value(series: Any) -> Optional[float]:
    values = _series_numeric_values(series)
    return values[-1] if values else None


def _regulatory_metric_value(
    regulatory_capital: Any,
    key: str,
) -> Optional[float]:
    if not isinstance(regulatory_capital, dict):
        return None
    return _cell_value(regulatory_capital.get(key))


def _latest_revenue_delta(inputs: dict[str, Any]) -> Optional[float]:
    revenue_series = inputs.get("adaptive_valuation_data", {}).get("revenue_history")
    values = _series_numeric_values(revenue_series)
    if len(values) >= 2:
        return values[-1] - values[-2]
    base_revenue = inputs.get("base_revenue")
    revenue_cagr = inputs.get("revenue_cagr_3y")
    if base_revenue is not None and revenue_cagr is not None:
        return base_revenue * revenue_cagr
    return None


def _company_sales_to_capital(inputs: dict[str, Any]) -> tuple[Optional[float], str]:
    """Use level invested capital instead of a noisy single-year revenue delta."""
    revenue = _positive_float(inputs.get("base_revenue"))
    debt = _to_float(inputs.get("total_debt"))
    equity = _to_float(inputs.get("bv_0"))
    cash = _to_float(inputs.get("cash"))
    if revenue is not None and None not in (debt, equity, cash):
        invested_capital = float(debt) + float(equity) - float(cash)
        if invested_capital > 0:
            return (
                _clamp(revenue / invested_capital, 0.1, 20.0),
                "latest revenue / (book equity + debt - cash); filing-backed operating-capital proxy",
            )
    assets = _positive_float(inputs.get("total_assets"))
    if revenue is not None and assets is not None:
        return (
            _clamp(revenue / assets, 0.1, 20.0),
            "latest revenue / total assets; filing-backed fallback because operating capital was unavailable",
        )
    return None, "unavailable: filing-backed operating capital inputs are incomplete"


def _stable_operating_margin(inputs: dict[str, Any]) -> tuple[Optional[float], str]:
    margins = [
        value for value in _series_numeric_values(inputs.get("operating_margin_history"))[-5:]
        if -0.20 <= value <= 0.80
    ]
    if len(margins) >= 3:
        return median(margins), "median of up to five comparable annual SEC operating margins"
    return None, "latest validated consensus margin; historical margin coverage was insufficient"


def _mature_terminal_wacc(
    current_wacc: float,
    components: Optional[dict[str, Any]],
    telemetry: dict[str, Any],
    perpetual_growth: float,
) -> tuple[float, str]:
    """Fade beta toward one while preserving the sourced capital structure."""
    risk_free = _to_float(telemetry.get("risk_free_rate"))
    mrp = _to_float(telemetry.get("market_risk_premium"))
    if risk_free is None or mrp is None:
        return current_wacc, "current WACC retained because mature beta inputs were unavailable"
    country_premium = _to_float(telemetry.get("country_risk_premium")) or 0.0
    mature_cost_of_equity = risk_free + mrp + country_premium
    weight_equity = _to_float((components or {}).get("weight_equity"))
    weight_debt = _to_float((components or {}).get("weight_debt"))
    debt_after_tax = _to_float((components or {}).get("cost_of_debt_after_tax"))
    if None not in (weight_equity, weight_debt, debt_after_tax):
        mature = (
            float(weight_equity) * mature_cost_of_equity
            + float(weight_debt) * float(debt_after_tax)
        )
    else:
        mature = mature_cost_of_equity
    return (
        max(mature, perpetual_growth + 0.005),
        "risk-free rate + beta(1.0) * market risk premium, using sourced debt weights when available",
    )


def _rnd_amortization_life(inputs: dict[str, Any]) -> int:
    text = " ".join(str(inputs.get(key) or "").lower() for key in (
        "sic_description", "finnhub_industry",
    ))
    return 3 if "software" in text else 5


def _consensus_anchor_growth(inputs: dict[str, Any]) -> Optional[float]:
    base_revenue = _positive_float(inputs.get("base_revenue"))
    base_year = inputs.get("base_fiscal_year")
    if base_revenue is None:
        return None
    rows: list[tuple[int, float]] = []
    for row in inputs.get("analyst_estimates") or []:
        try:
            year = int(str(row.get("date"))[:4])
            revenue = float(row.get("revenueAvg"))
        except (TypeError, ValueError):
            continue
        if revenue > 0 and (base_year is None or year > base_year):
            rows.append((year, revenue))
    if len(rows) < 2:
        return None
    rows.sort(key=lambda item: item[0])
    return rows[0][1] / base_revenue - 1.0


def _with_optional_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _build_engine_metadata(
    methodology: ValuationMethodology,
    result: dict[str, Any],
) -> dict[str, Any]:
    if result.get("fallback_reason"):
        return _with_optional_values({
            "fallback_reason": result.get("fallback_reason"),
            "rnd_history_validation_error": result.get("rnd_history_validation_error"),
            "rnd_capitalization_applied": result.get("rnd_capitalization_applied"),
        })

    if methodology == ValuationMethodology.TECH:
        current_year_rnd = result.get("current_year_rnd")
        amortization = result.get("amortization_of_rnd")
        base_revenue = result.get("base_revenue")
        adjusted_ebit = result.get("adjusted_ebit")
        capitalized_adjustment = (
            abs(current_year_rnd - amortization)
            if current_year_rnd is not None and amortization is not None
            else None
        )
        adjusted_margin = (
            adjusted_ebit / base_revenue
            if adjusted_ebit is not None and base_revenue
            else None
        )
        return _with_optional_values(
            {
                "model_version": result.get("model_version") or "capitalized_rnd_v1",
                "forecast_basis": result.get("forecast_basis"),
                "consensus_coverage": result.get("consensus_coverage"),
                "consensus_horizon_sensitivity": result.get(
                    "consensus_horizon_sensitivity"
                ),
                "capitalized_rnd_adjustment": capitalized_adjustment,
                "capitalized_rnd_asset": result.get("capitalized_rnd_asset"),
                "rnd_ebit_adjustment": result.get("rnd_ebit_adjustment"),
                "rnd_nopat_adjustment": result.get("rnd_nopat_adjustment"),
                "rnd_tax_benefit": result.get("rnd_tax_benefit"),
                "rnd_normalization_basis": "consecutive annual USD observations; straight-line research asset using the classification life",
                "adjusted_ebit_margin": adjusted_margin,
                "assumed_amortization_years": result.get(
                    "rnd_amortization_period_years"
                ),
                "terminal_roic": result.get("terminal_roic"),
                "terminal_reinvestment_rate": result.get("terminal_reinvestment_rate"),
            }
        )

    if methodology == ValuationMethodology.FINANCIAL:
        first_projection = next(iter(result.get("asset_projections") or []), {})
        projected_loan_growth = first_projection.get("asset_growth_rate")
        return _with_optional_values(
            {
                "tier_1_capital_ratio_used": result.get("tier1_capital_ratio"),
                "projected_loan_growth": projected_loan_growth,
                "discount_rate_type": "Cost of Equity (Ke)",
            }
        )

    if methodology == ValuationMethodology.CYCLICAL:
        return _with_optional_values(
            {
                "10_year_historical_median_margin": result.get("normalized_margin"),
                "normalized_base_ebit_generated": result.get(
                    "normalized_base_ebit"
                ),
            }
        )

    return {}


def _standardized_projection_years(
    methodology: ValuationMethodology,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    if methodology == ValuationMethodology.FINANCIAL:
        standardized: list[dict[str, Any]] = []
        for row in result.get("asset_projections") or []:
            standardized.append(
                _with_optional_values(
                    {
                        "year": row.get("year"),
                        "net_income": row.get("net_income"),
                        "net_income_growth": row.get("net_income_growth_rate"),
                        "total_assets": row.get("total_assets"),
                        "asset_growth_rate": row.get("asset_growth_rate"),
                        "change_in_total_assets": row.get(
                            "change_in_total_assets"
                        ),
                        "tier_1_capital_ratio_used": row.get(
                            "tier1_capital_ratio"
                        ),
                        "capital_deduction_label": (
                            "Required Regulatory Capital"
                        ),
                        "capital_deduction_value": row.get("required_capital"),
                        "free_cash_flow_to_equity": row.get("fcfe"),
                    }
                )
            )
        return standardized

    standardized = []
    revenue_projections = result.get("revenue_projections") or []
    for row in revenue_projections:
        standardized_row = _with_optional_values(
            {
                "year": row.get("year"),
                "fiscal_year": row.get("fiscal_year"),
                "forecast_stage": row.get("forecast_stage"),
                "source_status": row.get("source_status"),
                "revenue": row.get("revenue"),
                "revenue_growth": row.get("growth_rate"),
                "ebit_margin": row.get("ebit_margin"),
                "ebit": row.get("ebit"),
                "reported_consensus_ebit": row.get("reported_consensus_ebit"),
                "reported_consensus_ebit_margin": row.get("reported_consensus_ebit_margin"),
                "rnd_ebit_margin_adjustment": row.get("rnd_ebit_margin_adjustment"),
                "tax_rate": row.get("tax_rate"),
                "nopat": row.get("nopat"),
                "sales_to_capital_ratio": row.get("sales_to_capital_ratio"),
                "capital_deduction_label": "Reinvestment",
                "capital_deduction_value": row.get("reinvestment"),
                "unlevered_free_cash_flow": row.get("free_cash_flow"),
                "wacc": row.get("wacc"),
                "discount_factor": row.get("discount_factor"),
                "present_value": row.get("present_value"),
                "shares_outstanding": row.get("shares_outstanding"),
                "source_refs": row.get("source_refs"),
            }
        )
        row.update(standardized_row)
        standardized.append(standardized_row)
    return standardized


def _sample_std(values: list[float]) -> float:
    valid = [value for value in values if value is not None]
    if len(valid) < 2:
        return 0.0
    mean = sum(valid) / len(valid)
    variance = sum((value - mean) ** 2 for value in valid) / (len(valid) - 1)
    return variance ** 0.5


def _historical_revenue_growth_rates(inputs: dict[str, Any]) -> list[float]:
    revenue_series = inputs.get("adaptive_valuation_data", {}).get("revenue_history")
    values = [value for value in _series_numeric_values(revenue_series) if value > 0]
    growth_rates: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous > 0:
            growth_rates.append((current / previous) - 1)
    return growth_rates


def _base_operating_margin(
    methodology: ValuationMethodology,
    values: dict[str, Any],
    result: dict[str, Any],
) -> Optional[float]:
    if methodology == ValuationMethodology.FINANCIAL:
        return None
    if methodology == ValuationMethodology.CYCLICAL:
        normalized_margin = result.get("normalized_margin")
        if normalized_margin is not None:
            return normalized_margin
    operating_income = values.get("operating_income")
    base_revenue = values.get("base_revenue")
    if operating_income is not None and base_revenue:
        return operating_income / base_revenue
    if values.get("ebit_margin") is not None:
        return values["ebit_margin"]
    return result.get("base_ebit_margin")


def _build_adaptive_engine_runner(
    methodology: ValuationMethodology,
    values: dict[str, Any],
    *,
    depreciation_amortization: float,
    change_in_nwc: float,
    historical_change_in_revenue: Optional[float],
):
    def normalized(result: dict[str, Any]) -> dict[str, Any]:
        adr_ratio = values.get("adr_ratio") or 1.0
        equity_value = result.get("equity_value")
        if equity_value is not None:
            result["computed_fair_value"] = normalize_equity_value_per_traded_share(
                equity_value, values["shares_outstanding"], adr_ratio
            )
            result["adr_ratio"] = adr_ratio
            result["adr_ratio_applied"] = False  # Not applied as multiplier since shares_outstanding is already ADRs
            result["share_normalization_basis"] = "equity_value_usd / listed_shares"
        return result

    def run_engine(
        revenue_growth: float,
        operating_margin: Optional[float],
    ) -> dict[str, Any]:
        if methodology == ValuationMethodology.FINANCIAL:
            return normalized(calculate_fcfe(
                net_income=values["net_income"],
                total_assets=values["total_assets"],
                shares_outstanding=values["shares_outstanding"],
                cost_of_equity=values["cost_of_equity"],
                tier1_capital_ratio=values["tier1_capital_ratio"],
                net_income_growth_rate=revenue_growth,
                asset_growth_rate=revenue_growth,
                perpetual_growth_rate=values["perpetual_growth_rate"],
                projection_years=values["projection_years"],
                risk_free_rate=values["risk_free_rate"],
            ))

        selected_margin = (
            operating_margin
            if operating_margin is not None
            else values.get("ebit_margin")
        )
        if methodology == ValuationMethodology.TECH:
            if selected_margin is None:
                selected_margin = values["operating_income"] / values["base_revenue"]
            return normalized(calculate_growth_multistage_dcf(
                base_revenue=values["base_revenue"],
                operating_income=values["operating_income"],
                tax_rate=values["effective_tax_rate"],
                shares_outstanding=values["shares_outstanding"],
                total_debt=values["total_debt"],
                cash_and_equivalents=values["cash"],
                current_wacc=values["wacc"],
                terminal_wacc=values["terminal_wacc"],
                stage_1_growth_rate=revenue_growth,
                perpetual_growth_rate=values["perpetual_growth_rate"],
                projection_years=values["projection_years"],
                sales_to_capital=values["sales_to_capital"],
                consensus_estimates=values["analyst_estimates"],
                base_fiscal_year=values["base_fiscal_year"],
                stable_ebit_margin=values["stable_ebit_margin"],
                trailing_rnd=values["r_and_d_history"],
                rnd_amortization_years=values["rnd_amortization_years"],
                apply_driver_override=True,
                operating_margin_override=selected_margin,
            ))

        if methodology == ValuationMethodology.CYCLICAL:
            if operating_margin is None:
                historical_margins = _series_numeric_values(
                    values["operating_margin_history"]
                )
            else:
                historical_margins = [operating_margin]
            return normalized(calculate_normalized_median_dcf(
                base_revenue=values["base_revenue"],
                historical_operating_margins=historical_margins,
                tax_rate=values["effective_tax_rate"],
                capex=values["capex"],
                depreciation_amortization=depreciation_amortization,
                change_in_nwc=change_in_nwc,
                shares_outstanding=values["shares_outstanding"],
                total_debt=values["total_debt"],
                cash_and_equivalents=values["cash"],
                wacc=values["wacc"],
                stage_1_growth_rate=revenue_growth,
                perpetual_growth_rate=values["perpetual_growth_rate"],
                projection_years=values["projection_years"],
                historical_change_in_revenue=historical_change_in_revenue,
                risk_free_rate=values["risk_free_rate"],
            ))

        return normalized(calculate_standard_driver_dcf(
            base_revenue=values["base_revenue"],
            ebit_margin=selected_margin,
            tax_rate=values["effective_tax_rate"],
            capex=values["capex"],
            depreciation_amortization=depreciation_amortization,
            change_in_nwc=change_in_nwc,
            shares_outstanding=values["shares_outstanding"],
            total_debt=values["total_debt"],
            cash_and_equivalents=values["cash"],
            wacc=values["wacc"],
            stage_1_growth_rate=revenue_growth,
            perpetual_growth_rate=values["perpetual_growth_rate"],
            projection_years=values["projection_years"],
            historical_change_in_revenue=historical_change_in_revenue,
            risk_free_rate=values["risk_free_rate"],
        ))

    return run_engine


def _build_dcf_sensitivity_matrix(
    methodology: ValuationMethodology,
    values: dict[str, Any],
    *,
    base_operating_margin: Optional[float],
    depreciation_amortization: float,
    change_in_nwc: float,
    historical_change_in_revenue: Optional[float],
) -> list[dict[str, Any]]:
    base_growth = float(values["stage_1_growth_rate"])
    base_discount_rate = float(
        values["cost_of_equity"]
        if methodology == ValuationMethodology.FINANCIAL
        else values["wacc"]
    )
    growth_rates = [base_growth + offset for offset in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    discount_rates = [
        base_discount_rate + offset for offset in (-0.01, -0.005, 0.0, 0.005, 0.01)
    ]
    matrix: list[dict[str, Any]] = []
    for growth_rate in growth_rates:
        cells: list[dict[str, Any]] = []
        for selected_discount_rate in discount_rates:
            if selected_discount_rate <= values["perpetual_growth_rate"]:
                fair_value = None
            else:
                scenario_values = deepcopy(values)
                if methodology == ValuationMethodology.FINANCIAL:
                    scenario_values["cost_of_equity"] = selected_discount_rate
                else:
                    scenario_values["wacc"] = selected_discount_rate
                runner = _build_adaptive_engine_runner(
                    methodology,
                    scenario_values,
                    depreciation_amortization=depreciation_amortization,
                    change_in_nwc=change_in_nwc,
                    historical_change_in_revenue=historical_change_in_revenue,
                )
                result = runner(growth_rate, base_operating_margin)
                candidate = result.get("computed_fair_value")
                fair_value = (
                    float(candidate)
                    if candidate is not None and math.isfinite(candidate)
                    else None
                )
            cells.append(
                {
                    "discount_rate": selected_discount_rate,
                    "fair_value": fair_value,
                }
            )
        matrix.append({"growth_rate": growth_rate, "cells": cells})
    return matrix


@router.get("/inputs", response_model=ValuationInputsResponse)
def get_inputs(ticker: str):
    inputs = get_valuation_inputs(ticker)
    adaptive_data = inputs.get("adaptive_valuation_data") or {}
    return {
        "ticker": ticker.upper(),
        "status": "success" if inputs else "unavailable",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "data": inputs,
        "adaptive_valuation_data": adaptive_data,
        "warnings": [] if inputs else ["Valuation inputs are unavailable."],
    }


@router.get("/methodology", response_model=ValuationMethodologyResponse)
def get_methodology(ticker: str):
    inputs = get_valuation_inputs(ticker)
    adaptive_data = inputs.get("adaptive_valuation_data") or {}
    sic_code = inputs.get("sic_code") or adaptive_data.get("sic_code")
    methodology = get_valuation_methodology(sic_code, finnhub_industry=inputs.get("finnhub_industry"))
    logger.info(
        "Routed valuation methodology",
        extra={
            "ticker": ticker.upper(),
            "sic_code": sic_code,
            "valuation_methodology": methodology.value,
        },
    )
    return {
        "ticker": ticker.upper(),
        "status": "success" if inputs else "unavailable",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "methodology": methodology.value,
        "sic_code": sic_code,
        "sic_description": (
            inputs.get("sic_description")
            or adaptive_data.get("sic_description")
        ),
        "adaptive_valuation_data": adaptive_data,
        "warnings": [] if inputs else ["Valuation inputs are unavailable."],
    }

@router.get("/asset-based", response_model=ValuationResponse)
def get_asset_based(
    ticker: str,
    total_assets: Optional[float] = None,
    total_liabilities: Optional[float] = None,
    goodwill: Optional[float] = None,
    intangible_assets: Optional[float] = None,
    shares_outstanding: Optional[float] = None
):
    try:
        reject_non_finite_query_values(
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            goodwill=goodwill,
            intangible_assets=intangible_assets,
            shares_outstanding=shares_outstanding,
        )
        inputs = get_valuation_inputs(ticker)
        
        values = {
            "total_assets": total_assets if total_assets is not None else inputs.get("total_assets"),
            "total_liabilities": total_liabilities if total_liabilities is not None else inputs.get("total_liabilities"),
            "goodwill": goodwill if goodwill is not None else inputs.get("goodwill"),
            "intangible_assets": intangible_assets if intangible_assets is not None else inputs.get("intangible_assets"),
            "shares_outstanding": shares_outstanding if shares_outstanding is not None else inputs.get("shares_outstanding"),
            "adr_ratio": inputs.get("adr_ratio"),
        }
        missing = missing_required(
            values,
            ["total_assets", "total_liabilities", "goodwill", "intangible_assets", "shares_outstanding"],
        )
        if missing:
            return missing_input_response(ticker, "asset-based", missing, values)
        
        res = calculate_asset_based_valuation(
            values["total_assets"],
            values["total_liabilities"],
            values["goodwill"],
            values["intangible_assets"],
            values["shares_outstanding"]
        )
        res["total_liabilities_basis"] = inputs.get("total_liabilities_basis")
        res["goodwill_basis"] = (
            "query_override" if goodwill is not None else inputs.get("goodwill_basis")
        )
        res["goodwill_source_timestamp"] = (
            None if goodwill is not None else inputs.get("goodwill_source_timestamp")
        )
        res["intangible_assets_basis"] = (
            "query_override"
            if intangible_assets is not None
            else inputs.get("intangible_assets_basis")
        )
        res["intangible_assets_source_timestamp"] = (
            None
            if intangible_assets is not None
            else inputs.get("intangible_assets_source_timestamp")
        )
        res["asset_input_warnings"] = inputs.get("asset_input_warnings", [])
        current_price = get_valuation_telemetry(ticker).get("current_price")
        if current_price is not None and current_price > 0:
            res["scenario_margin_of_safety_percentage"] = {
                "standard_nav": (
                    (res["standard_nav_per_share"] - current_price) / current_price * 100
                ),
                "tangible_nav": (
                    (res["tangible_net_net_per_share"] - current_price) / current_price * 100
                ),
            }
        else:
            res["scenario_margin_of_safety_percentage"] = {
                "standard_nav": None,
                "tangible_nav": None,
            }
        res["scenario_margin_of_safety_basis"] = (
            "(selected_backend_nav_per_share - sourced_current_price) / sourced_current_price * 100"
        )
        res["adr_ratio"] = values.get("adr_ratio") or 1.0
        res["adr_ratio_applied"] = False
        return format_response(
            ticker, 
            res["computed_fair_value"], 
            "CALCULATED", 
            res
        )
    except Exception as e:
        return invalid_input_response(ticker, "asset-based", e)

@router.get("/dcf", response_model=ValuationResponse)
def get_dcf(
    ticker: str,
    cfo: Optional[float] = None,
    capex: Optional[float] = None,
    base_revenue: Optional[float] = None,
    ebit_margin: Optional[float] = None,
    effective_tax_rate: Optional[float] = None,
    reinvestment_rate: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    total_debt: Optional[float] = None,
    cash: Optional[float] = None,
    wacc: Optional[float] = None,
    discount_rate: Optional[float] = None,
    stage_1_growth_rate: Optional[float] = None,
    implied_target_price: Optional[float] = None,
    perpetual_growth_rate: float = 0.02,
    projection_years: int = Query(15, ge=1, le=30)
):
    methodology = ValuationMethodology.STANDARD
    try:
        reject_non_finite_query_values(
            cfo=cfo,
            capex=capex,
            base_revenue=base_revenue,
            ebit_margin=ebit_margin,
            effective_tax_rate=effective_tax_rate,
            reinvestment_rate=reinvestment_rate,
            shares_outstanding=shares_outstanding,
            total_debt=total_debt,
            cash=cash,
            wacc=wacc,
            discount_rate=discount_rate,
            stage_1_growth_rate=stage_1_growth_rate,
            implied_target_price=implied_target_price,
            perpetual_growth_rate=perpetual_growth_rate,
        )
        inputs = get_valuation_inputs(ticker)
        telemetry = get_valuation_telemetry(ticker)

        routing_methodology = get_valuation_methodology(
            inputs.get("sic_code"),
            finnhub_industry=inputs.get("finnhub_industry"),
        )
        sotp_cfg = get_sotp_config(
            methodology=routing_methodology.value,
            sic_description=inputs.get("sic_description"),
            industry=inputs.get("finnhub_industry"),
        )
        classification = get_cached_company_classification(ticker)
        if sotp_cfg is None:
            if classification is not None:
                sotp_cfg = get_sotp_config(
                    classification=classification,
                    methodology=routing_methodology.value,
                    sic_description=inputs.get("sic_description"),
                    industry=inputs.get("finnhub_industry"),
                )
        if sotp_cfg is not None:
            projection_years = 15
            
        selected_total_debt = total_debt if total_debt is not None else inputs.get("total_debt")
        selected_tax_rate = (
            effective_tax_rate
            if effective_tax_rate is not None
            else inputs.get("effective_tax_rate")
        )
        if selected_tax_rate is None:
            selected_tax_rate = 0.21
        market_cap = telemetry.get("market_cap")
        cost_of_equity = telemetry.get("cost_of_equity")
        interest_expense = inputs.get("interest_expense")
        wacc_components = None
        for label, override in {
            "discount_rate": discount_rate,
            "wacc": wacc,
            "stage_1_growth_rate": stage_1_growth_rate,
            "implied_target_price": implied_target_price,
            "perpetual_growth_rate": perpetual_growth_rate,
        }.items():
            if override is not None and not math.isfinite(override):
                raise ValueError(f"{label} must be finite.")
        if implied_target_price is not None and implied_target_price <= 0:
            raise ValueError("implied_target_price must be positive.")

        selected_wacc = discount_rate if discount_rate is not None else wacc
        wacc_basis = (
            "discount_rate_query_override"
            if discount_rate is not None
            else "query_override" if wacc is not None else None
        )
        wacc_missing_inputs: list[str] = []

        if selected_wacc is None:
            for key, value in {
                "market_cap": market_cap,
                "cost_of_equity": cost_of_equity,
                "total_debt": selected_total_debt,
                "effective_tax_rate": selected_tax_rate,
            }.items():
                if value is None:
                    wacc_missing_inputs.append(key)
            if selected_total_debt is not None and selected_total_debt > 0 and interest_expense is None:
                wacc_missing_inputs.append("interest_expense")

            if not wacc_missing_inputs:
                debt_for_weight = max(selected_total_debt or 0.0, 0.0)
                invested_capital = market_cap + debt_for_weight
                if invested_capital > 0:
                    weight_equity = market_cap / invested_capital
                    weight_debt = debt_for_weight / invested_capital
                    raw_cost_of_debt = (
                        abs(interest_expense) / debt_for_weight
                        if debt_for_weight > 0
                        else 0.0
                    )
                    cost_of_debt = min(raw_cost_of_debt, 0.20)
                    cost_of_debt_after_tax = cost_of_debt * (1 - selected_tax_rate)
                    selected_wacc = (weight_equity * cost_of_equity) + (
                        weight_debt * cost_of_debt_after_tax
                    )
                    wacc_basis = "true_wacc_market_cap_debt_interest_tax"
                    wacc_components = {
                        "market_cap": market_cap,
                        "total_debt": debt_for_weight,
                        "invested_capital": invested_capital,
                        "weight_equity": weight_equity,
                        "weight_debt": weight_debt,
                        "risk_free_rate": telemetry.get("risk_free_rate"),
                        "beta": telemetry.get("beta"),
                        "market_risk_premium": telemetry.get("market_risk_premium"),
                        "cost_of_equity": cost_of_equity,
                        "interest_expense": interest_expense,
                        "cost_of_debt": cost_of_debt,
                        "raw_cost_of_debt": raw_cost_of_debt,
                        "cost_of_debt_cap": 0.20,
                        "cost_of_debt_capped": raw_cost_of_debt > 0.20,
                        "effective_tax_rate": selected_tax_rate,
                        "cost_of_debt_after_tax": cost_of_debt_after_tax,
                        "wacc": selected_wacc,
                    }
            elif all(k in ["interest_expense", "total_debt", "cost_of_debt"] for k in wacc_missing_inputs) and cost_of_equity is not None:
                selected_wacc = cost_of_equity
                wacc_basis = "cost_of_equity_fallback_debt_metrics_unavailable"
                wacc_missing_inputs = []
                wacc_components = {
                    "market_cap": market_cap,
                    "total_debt": max(selected_total_debt or 0.0, 0.0),
                    "risk_free_rate": telemetry.get("risk_free_rate"),
                    "beta": telemetry.get("beta"),
                    "market_risk_premium": telemetry.get("market_risk_premium"),
                    "cost_of_equity": cost_of_equity,
                    "interest_expense": None,
                    "wacc": selected_wacc,
                    "fallback_reason": "Debt metrics unavailable; using cost of equity as a conservative WACC fallback.",
                }
        
        selected_cost_of_equity = (
            discount_rate
            if routing_methodology == ValuationMethodology.FINANCIAL
            and discount_rate is not None
            else cost_of_equity
        )
        selected_sales_to_capital, sales_to_capital_basis = _company_sales_to_capital(inputs)
        stable_ebit_margin, stable_margin_basis = _stable_operating_margin(inputs)
        selected_terminal_wacc = None
        terminal_wacc_basis = None
        if selected_wacc is not None:
            selected_terminal_wacc, terminal_wacc_basis = _mature_terminal_wacc(
                selected_wacc,
                wacc_components,
                telemetry,
                perpetual_growth_rate,
            )
        consensus_anchor_growth = (
            _consensus_anchor_growth(inputs)
            if routing_methodology == ValuationMethodology.TECH else None
        )
        selected_stage_growth = (
            stage_1_growth_rate
            if stage_1_growth_rate is not None
            else consensus_anchor_growth
            if consensus_anchor_growth is not None
            else inputs.get("stage_1_growth_rate_default")
        )
        values = {
            "cfo": cfo if cfo is not None else inputs.get("cfo"),
            "capex": capex if capex is not None else inputs.get("capex"),
            "base_revenue": base_revenue if base_revenue is not None else inputs.get("base_revenue"),
            "ebit_margin": ebit_margin if ebit_margin is not None else inputs.get("ebit_margin"),
            "effective_tax_rate": selected_tax_rate,
            "reinvestment_rate": reinvestment_rate if reinvestment_rate is not None else inputs.get("reinvestment_rate"),
            "shares_outstanding": shares_outstanding if shares_outstanding is not None else inputs.get("shares_outstanding"),
            "total_debt": selected_total_debt,
            "cash": cash if cash is not None else inputs.get("cash"),
            "wacc": selected_wacc,
            "terminal_wacc": selected_terminal_wacc,
            "terminal_wacc_basis": terminal_wacc_basis,
            "stage_1_growth_rate": selected_stage_growth,
            "perpetual_growth_rate": perpetual_growth_rate,
            "projection_years": projection_years,
            "market_cap": market_cap,
            "cost_of_equity": selected_cost_of_equity,
            "interest_expense": interest_expense,
            "risk_free_rate": telemetry.get("risk_free_rate"),
            "total_assets": inputs.get("total_assets"),
            "net_income": inputs.get("net_income"),
            "operating_income": inputs.get("operating_income"),
            "depreciation_amortization": inputs.get("depreciation_amortization"),
            "change_in_nwc": inputs.get("change_in_nwc"),
            "valuation_methodology": inputs.get("valuation_methodology"),
            "tier1_capital_ratio": _regulatory_metric_value(
                inputs.get("regulatory_capital"),
                "tier1_capital_ratio",
            ),
            "r_and_d_history": inputs.get("r_and_d_history", []),
            "rnd_amortization_years": _rnd_amortization_life(inputs),
            "analyst_estimates": inputs.get("analyst_estimates", []),
            "base_fiscal_year": inputs.get("base_fiscal_year"),
            "sales_to_capital": selected_sales_to_capital,
            "sales_to_capital_basis": sales_to_capital_basis,
            "stable_ebit_margin": stable_ebit_margin,
            "stable_ebit_margin_basis": stable_margin_basis,
            "book_equity": inputs.get("bv_0"),
            "operating_margin_history": inputs.get("operating_margin_history", []),
            "adr_ratio": inputs.get("adr_ratio"),
        }
        if wacc_missing_inputs and selected_wacc is None:
            values["wacc_missing_inputs"] = wacc_missing_inputs
        methodology = routing_methodology
        active_discount_rate = (
            values["cost_of_equity"]
            if methodology == ValuationMethodology.FINANCIAL
            else values["wacc"]
        )
        if (
            active_discount_rate is not None
            and perpetual_growth_rate >= active_discount_rate
        ):
            raise ValueError(
                "Discount rate must be greater than perpetual growth rate."
            )
        if methodology == ValuationMethodology.FINANCIAL:
            missing = missing_required(
                values,
                [
                    "net_income",
                    "total_assets",
                    "shares_outstanding",
                    "cost_of_equity",
                    "stage_1_growth_rate",
                    "perpetual_growth_rate",
                ],
            )
        elif methodology == ValuationMethodology.CYCLICAL:
            missing = missing_required(
                values,
                [
                    "capex",
                    "base_revenue",
                    "effective_tax_rate",
                    "shares_outstanding",
                    "total_debt",
                    "cash",
                    "wacc",
                    "stage_1_growth_rate",
                    "perpetual_growth_rate",
                ],
            )
            missing.extend(
                key for key in wacc_missing_inputs if key not in missing and selected_wacc is None
            )
        else:
            missing = missing_required(
                values,
                [
                    "capex",
                    "base_revenue",
                    "ebit_margin",
                    "effective_tax_rate",
                    "shares_outstanding",
                    "total_debt",
                    "cash",
                    "wacc",
                    "stage_1_growth_rate",
                    "perpetual_growth_rate",
                ],
            )
            if methodology == ValuationMethodology.TECH:
                missing.extend(
                    key for key in ("terminal_wacc", "sales_to_capital")
                    if values.get(key) is None and key not in missing
                )
            missing.extend(
                key for key in wacc_missing_inputs if key not in missing and selected_wacc is None
            )
        if inputs.get("is_foreign_private_issuer") and inputs.get("adr_ratio") is None:
            missing.append("adr_ratio")
        if inputs.get("fx_translation_unavailable"):
            missing.append("fx_translation")
        if missing:
            return missing_input_response(
                ticker,
                "dcf",
                missing,
                values,
                valuation_methodology=methodology.value,
            )
        if (
            methodology == ValuationMethodology.CYCLICAL
            and not _series_numeric_values(values["operating_margin_history"])
        ):
            if values.get("ebit_margin") is not None:
                values["operating_margin_history"] = [
                    {
                        "value": values["ebit_margin"],
                        "basis": "current_ebit_margin_fallback",
                    }
                ]
            else:
                return missing_input_response(
                    ticker,
                    "normalized-median-dcf",
                    ["operating_margin_history"],
                    values,
                    valuation_methodology=methodology.value,
                    engine_metadata={},
                )

        depreciation_amortization = values["depreciation_amortization"] or 0.0
        change_in_nwc = values["change_in_nwc"] or 0.0
        historical_change_in_revenue = _latest_revenue_delta(inputs)
        def generate_scenario_res(
            scenario_name: str,
            analyst_estimates_override: Optional[list[dict[str, Any]]] = None,
        ) -> dict:
            growth_modifier = 0.0
            margin_modifier = 0.0
            capex_modifier = 1.0
            if scenario_name == "bull":
                growth_modifier = 0.05
                margin_modifier = 0.02
                capex_modifier = 0.9
            elif scenario_name == "bear":
                growth_modifier = -0.05
                margin_modifier = -0.02
                capex_modifier = 1.15
            
            s_growth = (values["stage_1_growth_rate"] or 0) + growth_modifier
            s_ebit_margin = (values["ebit_margin"] or 0) + margin_modifier
            s_capex = values["capex"] * capex_modifier if values["capex"] is not None else 0.0
            
            if methodology == ValuationMethodology.FINANCIAL:
                return calculate_fcfe(
                    net_income=values["net_income"],
                    total_assets=values["total_assets"],
                    shares_outstanding=values["shares_outstanding"],
                    cost_of_equity=values["cost_of_equity"],
                    tier1_capital_ratio=values["tier1_capital_ratio"],
                    net_income_growth_rate=s_growth,
                    asset_growth_rate=s_growth,
                    perpetual_growth_rate=perpetual_growth_rate,
                    projection_years=projection_years,
                    risk_free_rate=values["risk_free_rate"],
                    adr_ratio=values.get("adr_ratio") or 1.0,
                )
            elif methodology == ValuationMethodology.TECH:
                operating_income = (
                    values["operating_income"]
                    if values["operating_income"] is not None
                    else values["base_revenue"] * values["ebit_margin"]
                )
                return calculate_growth_multistage_dcf(
                    base_revenue=values["base_revenue"],
                    operating_income=operating_income,
                    tax_rate=values["effective_tax_rate"],
                    shares_outstanding=values["shares_outstanding"],
                    adr_ratio=values.get("adr_ratio") or 1.0,
                    total_debt=values["total_debt"],
                    cash_and_equivalents=values["cash"],
                    current_wacc=values["wacc"],
                    terminal_wacc=values["terminal_wacc"],
                    stage_1_growth_rate=s_growth,
                    perpetual_growth_rate=perpetual_growth_rate,
                    projection_years=projection_years,
                    sales_to_capital=values["sales_to_capital"],
                    consensus_estimates=(
                        analyst_estimates_override
                        if analyst_estimates_override is not None
                        else values["analyst_estimates"]
                    ),
                    base_fiscal_year=values["base_fiscal_year"],
                    stable_ebit_margin=values["stable_ebit_margin"],
                    trailing_rnd=values["r_and_d_history"],
                    rnd_amortization_years=values["rnd_amortization_years"],
                    scenario=scenario_name,
                    apply_driver_override=(
                        scenario_name != "base"
                        or stage_1_growth_rate is not None
                        or ebit_margin is not None
                    ),
                    operating_margin_override=(
                        s_ebit_margin
                        if scenario_name != "base" or ebit_margin is not None
                        else None
                    ),
                )
            elif methodology == ValuationMethodology.CYCLICAL:
                return calculate_normalized_median_dcf(
                    base_revenue=values["base_revenue"],
                    historical_operating_margins=_series_numeric_values(
                        values["operating_margin_history"]
                    ),
                    tax_rate=values["effective_tax_rate"],
                    capex=s_capex,
                    depreciation_amortization=depreciation_amortization,
                    change_in_nwc=change_in_nwc,
                    shares_outstanding=values["shares_outstanding"],
                    adr_ratio=values.get("adr_ratio") or 1.0,
                    total_debt=values["total_debt"],
                    cash_and_equivalents=values["cash"],
                    wacc=values["wacc"],
                    stage_1_growth_rate=s_growth,
                    perpetual_growth_rate=perpetual_growth_rate,
                    projection_years=projection_years,
                    historical_change_in_revenue=historical_change_in_revenue,
                    risk_free_rate=values["risk_free_rate"],
                    scenario=scenario_name,
                )
            else:
                return calculate_standard_driver_dcf(
                    base_revenue=values["base_revenue"],
                    ebit_margin=values["ebit_margin"],
                    tax_rate=values["effective_tax_rate"],
                    capex=s_capex,
                    depreciation_amortization=depreciation_amortization,
                    change_in_nwc=change_in_nwc,
                    shares_outstanding=values["shares_outstanding"],
                    adr_ratio=values.get("adr_ratio") or 1.0,
                    total_debt=values["total_debt"],
                    cash_and_equivalents=values["cash"],
                    wacc=values["wacc"],
                    stage_1_growth_rate=s_growth,
                    perpetual_growth_rate=perpetual_growth_rate,
                    projection_years=projection_years,
                    historical_change_in_revenue=historical_change_in_revenue,
                    risk_free_rate=values["risk_free_rate"],
                    scenario=scenario_name,
                )
        res = generate_scenario_res("base")
        consensus_horizon_sensitivity: dict[str, Any] = {}
        if methodology == ValuationMethodology.TECH:
            coverage_years = list(
                (res.get("consensus_coverage") or {}).get("years") or []
            )
            # Removing the last provider year is diagnostic only. Keep at
            # least two consensus years so the truncated run follows the same
            # consensus-anchored engine rather than changing model families.
            if len(coverage_years) >= 3:
                removed_consensus_year = max(coverage_years)

                def _is_before_removed_year(row: dict[str, Any]) -> bool:
                    try:
                        return int(str(row.get("date"))[:4]) < removed_consensus_year
                    except (TypeError, ValueError):
                        return True

                truncated_estimates = [
                    row
                    for row in values.get("analyst_estimates") or []
                    if _is_before_removed_year(row)
                ]
                truncated_result = generate_scenario_res(
                    "base",
                    analyst_estimates_override=truncated_estimates,
                )
                full_fair_value = _to_float(res.get("computed_fair_value"))
                truncated_fair_value = _to_float(
                    truncated_result.get("computed_fair_value")
                )
                if full_fair_value is not None and truncated_fair_value is not None:
                    absolute_delta = abs(full_fair_value - truncated_fair_value)
                    relative_delta_percentage = (
                        absolute_delta / abs(full_fair_value) * 100.0
                        if full_fair_value != 0
                        else None
                    )
                    warning_threshold_percentage = 20.0
                    warning_triggered = (
                        relative_delta_percentage is not None
                        and relative_delta_percentage >= warning_threshold_percentage
                    )

                    consensus_rows_by_year: dict[int, dict[str, Any]] = {}
                    for row in values.get("analyst_estimates") or []:
                        try:
                            row_year = int(str(row.get("date"))[:4])
                        except (TypeError, ValueError):
                            continue
                        if row_year in coverage_years:
                            consensus_rows_by_year[row_year] = row

                    prior_consensus_years = [
                        year for year in coverage_years if year < removed_consensus_year
                    ]
                    prior_consensus_year = (
                        max(prior_consensus_years) if prior_consensus_years else None
                    )
                    last_revenue = _positive_float(
                        (consensus_rows_by_year.get(removed_consensus_year) or {}).get(
                            "revenueAvg"
                        )
                    )
                    prior_revenue = _positive_float(
                        (consensus_rows_by_year.get(prior_consensus_year) or {}).get(
                            "revenueAvg"
                        )
                        if prior_consensus_year is not None
                        else None
                    )
                    last_revenue_growth_percentage = (
                        (last_revenue / prior_revenue - 1.0) * 100.0
                        if last_revenue is not None and prior_revenue is not None
                        else None
                    )
                    last_revenue_analyst_count_raw = (
                        consensus_rows_by_year.get(removed_consensus_year) or {}
                    ).get("numAnalystsRevenue")
                    last_revenue_analyst_count_value = _to_float(
                        last_revenue_analyst_count_raw
                    )
                    last_revenue_analyst_count = (
                        int(last_revenue_analyst_count_value)
                        if last_revenue_analyst_count_value is not None
                        and last_revenue_analyst_count_value >= 0
                        and last_revenue_analyst_count_value.is_integer()
                        else None
                    )

                    consensus_horizon_sensitivity = {
                        "method": "remove_last_consensus_year",
                        "warning_code": "LAST_CONSENSUS_YEAR_MATERIAL_DEPENDENCY",
                        "warning_threshold_percentage": warning_threshold_percentage,
                        "assessment": (
                            "MATERIAL_DEPENDENCY"
                            if warning_triggered
                            else "STABLE_UNDER_TEST"
                        ),
                        "diagnostic_only": True,
                        "primary_value_basis": "full_valid_consensus",
                        "source_refs": ["fmp:analyst-estimates"],
                        "full_consensus_years": coverage_years,
                        "removed_consensus_year": removed_consensus_year,
                        "last_consensus_revenue_growth_percentage": (
                            last_revenue_growth_percentage
                        ),
                        "last_consensus_revenue_growth_basis": (
                            "last revenueAvg / prior revenueAvg - 1"
                        ),
                        "last_consensus_revenue_analyst_count": (
                            last_revenue_analyst_count
                        ),
                        "full_fair_value": full_fair_value,
                        "truncated_fair_value": truncated_fair_value,
                        "absolute_delta": absolute_delta,
                        "relative_delta_percentage": relative_delta_percentage,
                        "warning_triggered": warning_triggered,
                    }
                    res["consensus_horizon_sensitivity"] = (
                        consensus_horizon_sensitivity
                    )
        reported_fcf_0 = (
            values["cfo"] - values["capex"]
            if values.get("cfo") is not None and values.get("capex") is not None
            else None
        )
        res.update({
            "cfo": values["cfo"],
            "capex": values["capex"],
            "reported_fcf_0": reported_fcf_0,
            "maintenance_capex": inputs.get("maintenance_capex"),
            "base_revenue": values["base_revenue"],
            "base_revenue_basis": inputs.get("base_revenue_basis"),
            "revenue_cagr_3y": inputs.get("revenue_cagr_3y"),
            "revenue_cagr_years": inputs.get("revenue_cagr_years"),
            "ebit_margin": values["ebit_margin"],
            "operating_income": inputs.get("operating_income"),
            "effective_tax_rate": values["effective_tax_rate"],
            "tax_provision": inputs.get("tax_provision"),
            "ebt": inputs.get("ebt"),
            "interest_expense": interest_expense,
            "depreciation_amortization": inputs.get("depreciation_amortization"),
            "reinvestment_rate": values["reinvestment_rate"],
            "reinvestment_rate_basis": inputs.get("reinvestment_rate_basis"),
            "wacc": values["wacc"],
            "wacc_basis": wacc_basis,
            "wacc_components": wacc_components,
            "terminal_wacc": values.get("terminal_wacc"),
            "terminal_wacc_basis": values.get("terminal_wacc_basis"),
            "sales_to_capital_basis": values.get("sales_to_capital_basis"),
            "stable_ebit_margin_basis": values.get("stable_ebit_margin_basis"),
            "analyst_estimates": values.get("analyst_estimates", []),
            # Currency/FX provenance for non-USD filers (e.g. TSM reports in
            # TWD). Computed and used internally for normalization already;
            # expose it here too so a response consumer can audit that a
            # conversion happened rather than inferring it from magnitudes.
            "reported_currency": inputs.get("reported_currency"),
            "fx_translation": inputs.get("fx_translation"),
            "analyst_estimates_normalization": inputs.get("analyst_estimates_normalization"),
            "fcf_basis": inputs.get("fcf_basis"),
            "stage_1_growth_rate": values["stage_1_growth_rate"],
            "stage_1_growth_rate_basis": (
                "query_override"
                if stage_1_growth_rate is not None
                else "fmp_analyst_consensus_first_forecast_year"
                if consensus_anchor_growth is not None
                else "capped_annual_revenue_cagr_from_sec"
                if inputs.get("revenue_cagr_3y") is not None
                else "flat_growth_when_revenue_history_is_insufficient"
            ),
            "perpetual_growth_rate": perpetual_growth_rate,
            "projection_years": projection_years,
            "shares_outstanding": values["shares_outstanding"],
            "shares_outstanding_basis": inputs.get("shares_outstanding_basis"),
            "shares_outstanding_input_refs": inputs.get("shares_outstanding_input_refs", []),
            "weighted_average_shares": inputs.get("weighted_average_shares"),
            "total_debt": values["total_debt"],
            "cash": values["cash"],
            "driver_model": res.get("methodology"),
        })
        active_methodology = res.get("methodology") or methodology.value
        engine_metadata = _build_engine_metadata(methodology, res)
        projections = _standardized_projection_years(methodology, res)
        engine_runner = _build_adaptive_engine_runner(
            methodology,
            values,
            depreciation_amortization=depreciation_amortization,
            change_in_nwc=change_in_nwc,
            historical_change_in_revenue=historical_change_in_revenue,
        )
        base_operating_margin = _base_operating_margin(methodology, values, res)
        first_projection = next(iter(res.get("revenue_projections") or []), {})
        simulation_base_operating_margin = (
            _to_float(first_projection.get("ebit_margin"))
            if methodology == ValuationMethodology.TECH else None
        )
        if simulation_base_operating_margin is None:
            simulation_base_operating_margin = base_operating_margin
        revenue_growth_volatility = _sample_std(
            revenue_growth_rates := _historical_revenue_growth_rates(inputs)
        )
        operating_margin_history = _series_numeric_values(
            values["operating_margin_history"]
        )
        operating_margin_volatility = _sample_std(
            operating_margin_history
        )
        monte_carlo_results: dict[str, float] = {}
        implied_expectations: dict[str, Any] = {}
        computational_warnings: list[str] = []
        if consensus_horizon_sensitivity.get("warning_triggered"):
            computational_warnings.append(
                "LAST_CONSENSUS_YEAR_MATERIAL_DEPENDENCY: Removing consensus year "
                f"{consensus_horizon_sensitivity['removed_consensus_year']} changes fair value "
                f"from ${consensus_horizon_sensitivity['full_fair_value']:.2f} to "
                f"${consensus_horizon_sensitivity['truncated_fair_value']:.2f} "
                f"({consensus_horizon_sensitivity['relative_delta_percentage']:.1f}%), "
                "which meets or exceeds the 20% materiality threshold."
            )
        estimates_normalization = inputs.get("analyst_estimates_normalization") or {}
        if estimates_normalization.get("status") == "unavailable" and estimates_normalization.get("reason"):
            computational_warnings.append(
                f"Analyst consensus unavailable: {estimates_normalization['reason']}"
            )
        if res.get("margin_consensus_rejected") and res.get("margin_consensus_rejection_reason"):
            computational_warnings.append(
                f"Analyst margin consensus rejected: {res['margin_consensus_rejection_reason']}"
            )
        revenue_history_sufficient = len(revenue_growth_rates) >= 2
        margin_history_sufficient = (
            methodology == ValuationMethodology.FINANCIAL
            or len(operating_margin_history) >= 2
        )
        if revenue_history_sufficient and margin_history_sufficient:
            try:
                monte_carlo_results = run_monte_carlo_simulation(
                    engine_runner=engine_runner,
                    base_revenue_growth=values["stage_1_growth_rate"],
                    base_operating_margin=simulation_base_operating_margin,
                    revenue_growth_volatility=revenue_growth_volatility,
                    operating_margin_volatility=operating_margin_volatility,
                    live_market_price=telemetry.get("current_price"),
                )
            except Exception as exc:
                logger.warning(
                    "Monte Carlo valuation layer failed",
                    extra={"ticker": ticker.upper(), "error_type": type(exc).__name__},
                )
                computational_warnings.append(
                    "MONTE_CARLO_UNAVAILABLE: probabilistic calculation failed."
                )
        else:
            missing_histories = []
            if not revenue_history_sufficient:
                missing_histories.append("revenue")
            if not margin_history_sufficient:
                missing_histories.append("operating margin")
            computational_warnings.append(
                "Monte Carlo unavailable: insufficient comparable annual history "
                f"for historical volatility ({', '.join(missing_histories)})."
            )

        live_market_price = telemetry.get("current_price")
        solver_target_price = implied_target_price or live_market_price
        if solver_target_price is not None:
            try:
                # Engine runner already emits traded-share/ADR fair value.
                # Compare it directly with the live traded-share market price.
                implied_expectations = calculate_implied_expectations(
                    engine_runner=engine_runner,
                    live_market_price=solver_target_price,
                    base_revenue_growth=values["stage_1_growth_rate"],
                    base_operating_margin=simulation_base_operating_margin,
                )
            except Exception as exc:
                logger.warning(
                    "Implied expectations layer failed",
                    extra={"ticker": ticker.upper(), "error_type": type(exc).__name__},
                )
                computational_warnings.append(
                    "IMPLIED_EXPECTATIONS_UNAVAILABLE: solver calculation failed."
                )
        res.update(
            {
                "valuation_methodology": active_methodology,
                "engine_metadata": engine_metadata,
                "projections": projections,
                "monte_carlo_results": monte_carlo_results,
                "implied_expectations": implied_expectations,
                "historical_revenue_growth_volatility": revenue_growth_volatility,
                "historical_operating_margin_volatility": operating_margin_volatility,
                "computational_warnings": computational_warnings,
            }
        )
        # --- Config-driven SOTP layer -------------------------------------
        # Eligibility and segment templates are selected from company
        # classification rather than ticker allowlists.
        sotp_breakdown = None
        reverse_dcf_sotp = {
            "is_active": sotp_cfg is not None,
            "solver_available": False,
            "requested_target_price": solver_target_price,
            "model_fair_value": res.get("computed_fair_value"),
            "target_price": None,
            "implied_growth_rate": None,
            "years": 15 if sotp_cfg is not None else None,
            "horizon_years": 15 if sotp_cfg is not None else None,
            "classification_profile": sotp_cfg["profile"] if sotp_cfg is not None else None,
            "segments": [],
        }
        if sotp_cfg is not None:
            try:
                if sotp_cfg.get("segment_source") == "single_segment_fallback_unquantified_classification":
                    revenue_mix = inputs.get("revenue_mix") or {}
                    reported_segments = (
                        revenue_mix.get("revenue_mix", {}).get("business_segments", [])
                        if isinstance(revenue_mix, dict) else []
                    )
                    evidence_segments = [
                        {
                            "name": segment.get("name"),
                            "reported_revenue": segment.get("revenue"),
                            "revenue_percentage": segment.get("percentage"),
                            "currency": segment.get("currency"),
                            "period_end": segment.get("period_end"),
                            "source_status": "reported_fact",
                            "source": segment.get("source"),
                            "filing_url": segment.get("filing_url"),
                            "evidence": segment.get("evidence"),
                            "valuation_status": "unavailable_without_segment_margin_and_reinvestment_inputs",
                        }
                        for segment in reported_segments
                        if isinstance(segment, dict) and segment.get("name")
                    ]
                    sotp_breakdown = {
                        "ticker": ticker.upper(),
                        "status": "EVIDENCE_ONLY" if evidence_segments else "UNAVAILABLE",
                        "calculated_price": None,
                        "classification_profile": sotp_cfg["profile"],
                        "segment_source": "sec_reported_revenue_mix" if evidence_segments else sotp_cfg["segment_source"],
                        "segments": evidence_segments,
                        "warning": (
                            "Reported segment revenue is shown as evidence only; no segment value is calculated without segment margins and reinvestment inputs."
                            if evidence_segments else
                            "SOTP is unavailable because filing-backed quantified segment inputs are incomplete."
                        ),
                    }
                    reverse_dcf_sotp.update({
                        "is_active": False,
                        "solver_available": False,
                        "segment_source": sotp_breakdown["segment_source"],
                        "segments": evidence_segments,
                    })
                    computational_warnings.append(sotp_breakdown["warning"])
                    raise StopIteration
                from app.services.dynamic_valuation_router import (
                    ValuationRouter,
                    CompanyConfig,
                    SegmentConfig,
                )

                total_revenue = values.get("base_revenue", 0.0)
                shares_outstanding = values.get("shares_outstanding", 1.0)
                net_cash = values.get("cash", 0.0) - values.get("total_debt", 0.0)
                segment_configs = [
                    SegmentConfig(
                        name=seg["name"],
                        base_revenue=total_revenue * seg["base_revenue_fraction"],
                        target_margin=seg["target_margin"],
                        sales_to_capital=seg["sales_to_capital"],
                        is_high_growth=seg["is_high_growth"],
                    )
                    for seg in sotp_cfg["segments"]
                ]
                company_config = CompanyConfig(
                    ticker=ticker.upper(),
                    sector=sotp_cfg["sector"],
                    current_price=solver_target_price or 0.0,
                    shares_outstanding=shares_outstanding,
                    net_cash=net_cash,
                    wacc=values["wacc"],
                    segments=segment_configs,
                )
                sotp_router = ValuationRouter()
                sotp_res = sotp_router.route_and_evaluate(company_config)
                if sotp_res.get("status") == "success":
                    hg_name = sotp_res["high_growth_segment_name"]
                    implied_growth_pct = sotp_res["implied_high_growth_rate"] * 100
                    # Build per-segment breakdown with per-share values so the
                    # frontend stacked composition renders $/share bars.
                    segments_out = []
                    for seg in segment_configs:
                        if seg.is_high_growth:
                            ev_contribution = sotp_res["high_growth_ev"]
                            seg_entry = {
                                "name": seg.name,
                                "is_high_growth": True,
                                "ev_contribution": ev_contribution,
                                "value": ev_contribution / shares_outstanding,
                                "margin": seg.target_margin * 100,
                                "implied_growth": implied_growth_pct,
                            }
                        else:
                            ev_contribution = sotp_res["standard_evs"][seg.name]
                            seg_entry = {
                                "name": seg.name,
                                "is_high_growth": False,
                                "ev_contribution": ev_contribution,
                                "value": ev_contribution / shares_outstanding,
                                "margin": seg.target_margin * 100,
                            }
                        segments_out.append(seg_entry)
                    sotp_breakdown = {
                        "ticker": ticker.upper(),
                        "market_price": telemetry.get("current_price"),
                        "current_price": telemetry.get("current_price"),
                        "calculated_price": sotp_res["calculated_price"],
                        "total_ev": sotp_res["total_ev"],
                        "net_cash": net_cash,
                        "shares_outstanding": shares_outstanding,
                        "required_cagr": implied_growth_pct,
                        "horizon_years": 15,
                        "years": 15,
                        "high_growth_segment_name": hg_name,
                        "classification_profile": sotp_cfg["profile"],
                        "segments": segments_out,
                    }
                    reverse_dcf_sotp = {
                        "is_active": True,
                        "solver_available": True,
                        "requested_target_price": solver_target_price,
                        "model_fair_value": sotp_res["calculated_price"],
                        "target_price": sotp_res["calculated_price"],
                        "implied_growth_rate": implied_growth_pct,
                        "total_ev": sotp_res.get("total_ev", 0),
                        "net_cash": net_cash,
                        "years": 15,
                        "horizon_years": 15,
                        "high_growth_segment_name": hg_name,
                        "classification_profile": sotp_cfg["profile"],
                        "segments": segments_out,
                    }
                else:
                    reason = sotp_res.get("reason", "unknown")
                    computational_warnings.append(
                        f"SOTP solver did not converge: {reason}"
                    )
            except StopIteration:
                pass
            except Exception as exc:
                computational_warnings.append(
                    "SOTP_UNAVAILABLE: sum-of-the-parts calculation failed."
                )
                logger.warning(
                    "SOTP valuation layer failed",
                    extra={"ticker": ticker.upper(), "error_type": type(exc).__name__},
                )

        res_bull = generate_scenario_res("bull")
        res_bear = generate_scenario_res("bear")
        for scenario_result in (res, res_bull, res_bear):
            if scenario_result.get("equity_value") is not None:
                scenario_result["computed_fair_value"] = normalize_equity_value_per_traded_share(
                    scenario_result["equity_value"], values["shares_outstanding"], values.get("adr_ratio") or 1.0
                )

        sensitivity_matrix = _build_dcf_sensitivity_matrix(
            methodology,
            values,
            # The sensitivity center must replay the exact active base case.
            # For consensus-anchored TECH models, the first projected margin
            # already includes the validated provider trajectory and any R&D
            # adjustment. Using the current reported margin here applied a
            # second margin override and made the center disagree with the
            # headline DCF even though growth and WACC were unchanged.
            base_operating_margin=simulation_base_operating_margin,
            depreciation_amortization=depreciation_amortization,
            change_in_nwc=change_in_nwc,
            historical_change_in_revenue=historical_change_in_revenue,
        )
        sensitivity_center = (
            sensitivity_matrix[2]["cells"][2].get("fair_value")
            if len(sensitivity_matrix) >= 3
            and len(sensitivity_matrix[2].get("cells") or []) >= 3
            else None
        )

        forward_dcf = {
            "valuation_status": "CALCULATED",
            "fair_value": res["computed_fair_value"],
            "fcf_growth_rate": values.get("stage_1_growth_rate", 0),
            "wacc": (res.get("discount_rate", values.get("wacc", 0)) * 100) if res.get("discount_rate") is not None or values.get("wacc") is not None else None,
            "projections": projections,
            "sensitivity_matrix": sensitivity_matrix,
            "sensitivity_basis": {
                "scenario": "base",
                "center_growth_rate": values.get("stage_1_growth_rate"),
                "center_discount_rate": (
                    values.get("cost_of_equity")
                    if methodology == ValuationMethodology.FINANCIAL
                    else values.get("wacc")
                ),
                "discount_rate_driver": (
                    "cost_of_equity"
                    if methodology == ValuationMethodology.FINANCIAL
                    else "current_wacc"
                ),
                "center_fair_value": sensitivity_center,
                "overview_fair_value": res["computed_fair_value"],
                "calculation_basis": "active base-case inputs with only the matrix growth and discount-rate coordinates varied",
            },
            "scenarios": {
                "base": {
                    "projections": projections,
                    "harvest_start_year": res.get("harvest_start_year")
                },
                "bull": {
                    "projections": _standardized_projection_years(methodology, res_bull),
                    "harvest_start_year": res_bull.get("harvest_start_year")
                },
                "bear": {
                    "projections": _standardized_projection_years(methodology, res_bear),
                    "harvest_start_year": res_bear.get("harvest_start_year")
                }
            }
        }

        equity_value_check = res.get("equity_value")
        fair_value_check = res.get("computed_fair_value")
        if (equity_value_check is not None and equity_value_check <= 0) or (
            fair_value_check is not None and fair_value_check <= 0
        ):
            # A non-positive equity value is not a usable fair value estimate
            # (AGENTS.md: never present placeholder/impossible values as real
            # ones). This means projected reinvestment exceeded NOPAT across
            # enough of the forecast horizon that discounted cash flow never
            # recovers before the terminal year — surface why instead of a
            # number that reads as real.
            return unavailable_output_response(
                ticker,
                "dcf",
                "NEGATIVE_OR_ZERO_EQUITY_VALUE",
                (
                    "The model's projected reinvestment exceeds NOPAT across enough of the "
                    "forecast horizon that the discounted cash flow does not recover before "
                    "the terminal year, producing a non-positive equity value. Review the "
                    "sales-to-capital and margin assumptions in the DCF deep-dive."
                ),
                res,
                valuation_methodology=active_methodology,
                engine_metadata=engine_metadata,
            )

        return format_response(
            ticker,
            res["computed_fair_value"],
            "CALCULATED",
            res,
            valuation_methodology=active_methodology,
            engine_metadata=engine_metadata,
            projections=projections,
            monte_carlo_results=monte_carlo_results,
            implied_expectations=implied_expectations,
            sotp_breakdown=sotp_breakdown,
            forward_dcf=forward_dcf,
            reverse_dcf_sotp=reverse_dcf_sotp,
        )
    except Exception as e:
        return invalid_input_response(
            ticker,
            "dcf",
            e,
            valuation_methodology=methodology.value,
        )

@router.get("/ddm", response_model=ValuationResponse)
def get_ddm(
    ticker: str,
    dividends_paid: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    cost_of_equity: Optional[float] = None,
    historical_dividends: Optional[list[float]] = Query(None)
):
    try:
        if isinstance(historical_dividends, Param):
            historical_dividends = None
        reject_non_finite_query_values(
            dividends_paid=dividends_paid,
            shares_outstanding=shares_outstanding,
            cost_of_equity=cost_of_equity,
        )
        if historical_dividends is not None and (
            len(historical_dividends) > 100
            or any(not math.isfinite(value) for value in historical_dividends)
        ):
            raise ValueError("Historical dividends must contain at most 100 finite values.")
        inputs = get_valuation_inputs(ticker)
        telemetry = get_valuation_telemetry(ticker)
        
        values = {
            "dividends_paid": dividends_paid if dividends_paid is not None else inputs.get("dividends_paid"),
            "shares_outstanding": shares_outstanding if shares_outstanding is not None else inputs.get("shares_outstanding"),
            "cost_of_equity": cost_of_equity if cost_of_equity is not None else telemetry.get("cost_of_equity"),
            "historical_dividends": historical_dividends if historical_dividends is not None else inputs.get("historical_dividends", []),
            "adr_ratio": inputs.get("adr_ratio"),
        }
        missing = missing_required(values, ["dividends_paid", "shares_outstanding", "cost_of_equity"])
        if missing:
            return missing_input_response(ticker, "ddm", missing, values)
        
        hist_div = values["historical_dividends"]
        if len(hist_div) < 2:
            return missing_input_response(
                ticker,
                "ddm",
                ["historical_dividends"],
                values,
            )
        
        res = calculate_ddm_valuation(
            values["dividends_paid"],
            values["shares_outstanding"],
            hist_div,
            values["cost_of_equity"],
            values.get("adr_ratio") or 1.0
        )
        res["cost_of_equity"] = values["cost_of_equity"]
        
        ni = inputs.get("net_income", 0.0)
        payout_ratio = (values["dividends_paid"] / ni * 100) if ni else None
        res["payout_ratio"] = payout_ratio
        res["payout_ratio_basis"] = "dividends_paid / net_income * 100"
        
        current_price = telemetry.get("current_price")
        if not is_performance_cache_only():
            quote = get_yahoo_quote(ticker)
            current_price = quote.get("regularMarketPrice")
        dividend_yield = (
            res.get("annual_dividend_per_share", 0) / current_price
            if current_price and current_price > 0
            else None
        )
        res["dividend_yield"] = dividend_yield
        res["dividend_yield_basis"] = "annual_dividend_per_share / sourced_current_price"
        
        is_ddm_applicable = True
        applicability_reasons: list[str] = []
        if str(res.get("status", "")).startswith("DDM_INAPPLICABLE"):
            is_ddm_applicable = False
            applicability_reasons.append("No sourced dividend distribution is available.")
        if payout_ratio is not None and payout_ratio < 15.0:
            is_ddm_applicable = False
            applicability_reasons.append("Dividend payout ratio is below 15%.")
        if dividend_yield is not None and dividend_yield < 0.01:
            is_ddm_applicable = False
            applicability_reasons.append("Dividend yield is below 1%.")
        if res.get("dividend_growth_cagr", 0) >= values["cost_of_equity"]:
            is_ddm_applicable = False
            applicability_reasons.append("Dividend growth is not below cost of equity.")
            
        res["is_ddm_applicable"] = is_ddm_applicable
        res["applicability_reasons"] = list(dict.fromkeys(applicability_reasons))
        
        # Keep the public valuation contract consistent across all engines.
        # The engine-level ``APPLICABLE`` value is useful calculation detail,
        # but successful top-level responses must use ``CALCULATED`` so API
        # consumers do not mistake a valid DDM result for an unavailable one.
        status = "CALCULATED" if is_ddm_applicable else "INAPPLICABLE"
            
        return format_response(
            ticker, 
            res.get("computed_fair_value"),
            status, 
            res
        )
    except Exception as e:
        return invalid_input_response(ticker, "ddm", e)

@router.get("/relative", response_model=ValuationResponse)
def get_relative(
    ticker: str,
    target_eps: Optional[float] = None,
    target_bvps: Optional[float] = None,
    target_ebitda: Optional[float] = None,
    target_debt: Optional[float] = None,
    target_cash: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    included_peer_symbols: Annotated[
        Optional[list[str]], Query(alias="included_peer")
    ] = None,
):
    try:
        reject_non_finite_query_values(
            target_eps=target_eps,
            target_bvps=target_bvps,
            target_ebitda=target_ebitda,
            target_debt=target_debt,
            target_cash=target_cash,
            shares_outstanding=shares_outstanding,
        )
        if included_peer_symbols is not None and len(included_peer_symbols) > 20:
            raise ValueError("A maximum of 20 included peers is allowed.")
        inputs = get_valuation_inputs(ticker)
        
        values = {
            "target_eps": target_eps if target_eps is not None else inputs.get("target_eps"),
            "target_bvps": target_bvps if target_bvps is not None else inputs.get("target_bvps"),
            "target_ebitda": target_ebitda if target_ebitda is not None else inputs.get("target_ebitda"),
            "target_debt": target_debt if target_debt is not None else inputs.get("total_debt"),
            "target_cash": target_cash if target_cash is not None else inputs.get("cash"),
            "shares_outstanding": shares_outstanding if shares_outstanding is not None else inputs.get("shares_outstanding"),
            "adr_ratio": inputs.get("adr_ratio"),
        }
        missing_fundamentals = missing_required(
            values,
            ["target_eps", "target_bvps", "shares_outstanding"],
        )
        if missing_fundamentals:
            return missing_input_response(ticker, "relative", missing_fundamentals, values)
        
        available_by_symbol: dict[str, dict[str, Any]] = {}
        for peer in build_relative_peers(ticker):
            symbol = str(peer.get("symbol", "")).strip().upper()
            if symbol:
                available_by_symbol[symbol] = {**peer, "symbol": symbol}
        available_peers = list(available_by_symbol.values())
        if included_peer_symbols is None:
            selected_symbols = list(available_by_symbol)
        else:
            selected_symbols = list(dict.fromkeys(
                symbol.strip().upper()
                for symbol in included_peer_symbols
                if symbol and symbol.strip()
            ))
            unknown_symbols = [
                symbol for symbol in selected_symbols if symbol not in available_by_symbol
            ]
            if unknown_symbols:
                raise ValueError(
                    "Included peers are not available for this company: "
                    + ", ".join(unknown_symbols)
                )
            if not selected_symbols:
                raise ValueError("At least one available peer must be included.")

        peers = [available_by_symbol[symbol] for symbol in selected_symbols]
        values["peers"] = peers if peers else None
        missing = missing_required(values, ["peers"])
        if missing or not peers:
            return missing_input_response(ticker, "relative", ["peers"], values)

        is_financials = False
        sector = inputs.get("company_profile", {}).get("sector", "").lower()
        if "financial" in sector or "bank" in sector:
            is_financials = True
            
        res = calculate_relative_valuation(
            values["target_eps"], values["target_bvps"], values["target_ebitda"],
            values["target_debt"], values["target_cash"], values["shares_outstanding"], peers,
            values.get("adr_ratio") or 1.0,
            is_financials=is_financials
        )
        res["available_peers"] = available_peers
        res["included_peer_symbols"] = selected_symbols
        res["peer_selection_basis"] = (
            "user_selected_available_peers"
            if included_peer_symbols is not None
            else "all_available_peers"
        )
        
        return format_response(
            ticker, 
            res.get("computed_fair_value", 0), 
            "CALCULATED", 
            res
        )
    except Exception as e:
        return invalid_input_response(ticker, "relative", e)

@router.get("/residual-income", response_model=ValuationResponse)
def get_residual_income(
    ticker: str,
    bv_0: Optional[float] = None,
    net_income: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    cost_of_equity: Optional[float] = None,
    dividend_payout_ratio: float = 0.3,
    persistence_factor: float = 0.5
):
    try:
        reject_non_finite_query_values(
            bv_0=bv_0,
            net_income=net_income,
            shares_outstanding=shares_outstanding,
            cost_of_equity=cost_of_equity,
            dividend_payout_ratio=dividend_payout_ratio,
            persistence_factor=persistence_factor,
        )
        inputs = get_valuation_inputs(ticker)
        telemetry = get_valuation_telemetry(ticker)
        
        values = {
            "bv_0": bv_0 if bv_0 is not None else inputs.get("bv_0"),
            "net_income": net_income if net_income is not None else inputs.get("net_income"),
            "shares_outstanding": shares_outstanding if shares_outstanding is not None else inputs.get("shares_outstanding"),
            "cost_of_equity": cost_of_equity if cost_of_equity is not None else telemetry.get("cost_of_equity"),
            "dividend_payout_ratio": dividend_payout_ratio,
            "persistence_factor": persistence_factor,
            "adr_ratio": inputs.get("adr_ratio"),
        }
        missing = missing_required(
            values,
            ["bv_0", "net_income", "shares_outstanding", "cost_of_equity", "dividend_payout_ratio", "persistence_factor"],
        )
        if missing:
            return missing_input_response(ticker, "residual-income", missing, values)
        if inputs.get("is_foreign_private_issuer") and values["adr_ratio"] is None:
            return missing_input_response(ticker, "residual-income", ["adr_ratio"], values)
        if inputs.get("fx_translation_unavailable"):
            return missing_input_response(ticker, "residual-income", ["fx_translation"], values)
        
        res = calculate_residual_income_valuation(
            values["bv_0"], values["net_income"], values["shares_outstanding"],
            values["cost_of_equity"], dividend_payout_ratio, persistence_factor,
            values.get("adr_ratio") or 1.0
        )
        
        return format_response(
            ticker,
            res.get("computed_fair_value", 0),
            "CALCULATED", 
            res
        )
    except Exception as e:
        return invalid_input_response(ticker, "residual-income", e)
