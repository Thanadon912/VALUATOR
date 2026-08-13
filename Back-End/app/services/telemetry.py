import asyncio
import logging
import json
from defusedxml import ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic

import httpx

from app.core.runtime_paths import runtime_cache_path

logger = logging.getLogger(__name__)

TREASURY_YIELD_CURVE_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
)
RISK_FREE_CACHE_TTL_SECONDS = 6 * 60 * 60
TREASURY_REQUEST_TIMEOUT_SECONDS = 25.0
TREASURY_USER_AGENT = "USAStockAnalysis/1.0 risk-free-rate-cache"
RISK_FREE_CACHE_FILE = runtime_cache_path("risk_free_rate.json")

_risk_free_lock = Lock()
_risk_free_refresh_lock = Lock()
_risk_free_cache_updated_at = -float('inf')

# Cached value for the risk-free rate. The default is a fallback only; when the
# Treasury feed is reachable, it is replaced by the latest 10Y par yield.
GLOBAL_RISK_FREE_RATE = 0.04
GLOBAL_RISK_FREE_AS_OF: str | None = None
GLOBAL_RISK_FREE_SOURCE = "fallback_default"


def _treasury_xml_params(year: int) -> dict[str, str]:
    return {
        "data": "daily_treasury_yield_curve",
        "field_tdr_date_value": str(year),
    }


def _parse_latest_10y_from_xml(xml_text: str) -> tuple[float, str] | None:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    }
    root = ET.fromstring(xml_text)
    latest: tuple[str, float] | None = None

    for entry in root.findall("atom:entry", ns):
        properties = entry.find("atom:content/m:properties", ns)
        if properties is None:
            continue
        date_el = properties.find("d:NEW_DATE", ns)
        rate_el = properties.find("d:BC_10YEAR", ns)
        if date_el is None or rate_el is None or not date_el.text or not rate_el.text:
            continue
        try:
            rate = float(rate_el.text) / 100.0
        except ValueError:
            continue
        as_of = date_el.text.split("T", 1)[0]
        if latest is None or as_of > latest[0]:
            latest = (as_of, rate)

    if latest is None:
        return None
    as_of, rate = latest
    return rate, as_of


def _store_risk_free_rate(rate: float, as_of: str, source: str) -> float:
    global GLOBAL_RISK_FREE_RATE, GLOBAL_RISK_FREE_AS_OF, GLOBAL_RISK_FREE_SOURCE
    global _risk_free_cache_updated_at

    with _risk_free_lock:
        GLOBAL_RISK_FREE_RATE = rate
        GLOBAL_RISK_FREE_AS_OF = as_of
        GLOBAL_RISK_FREE_SOURCE = source
        _risk_free_cache_updated_at = monotonic()
    if source != "fallback_default":
        try:
            RISK_FREE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            RISK_FREE_CACHE_FILE.write_text(
                json.dumps(
                    {
                        "risk_free_rate": rate,
                        "risk_free_rate_as_of": as_of,
                        "risk_free_rate_source": source,
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "risk_free_rate_cache_persist_failed",
                extra={"error_type": type(exc).__name__},
            )
    return rate


def _load_disk_cached_risk_free_rate() -> float | None:
    global GLOBAL_RISK_FREE_RATE, GLOBAL_RISK_FREE_AS_OF, GLOBAL_RISK_FREE_SOURCE
    global _risk_free_cache_updated_at

    try:
        payload = json.loads(RISK_FREE_CACHE_FILE.read_text(encoding="utf-8"))
        rate = float(payload["risk_free_rate"])
        as_of = str(payload["risk_free_rate_as_of"])
        source = str(payload["risk_free_rate_source"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if rate <= 0 or source == "fallback_default":
        return None

    with _risk_free_lock:
        GLOBAL_RISK_FREE_RATE = rate
        GLOBAL_RISK_FREE_AS_OF = as_of
        GLOBAL_RISK_FREE_SOURCE = f"{source} (stale cache)"
        _risk_free_cache_updated_at = monotonic()
    return rate

async def fetch_treasury_risk_free_rate() -> float:
    """Fetch the latest 10-year Treasury par yield from the official XML feed."""
    # Both async and sync callers share one refresh gate. Running the sync
    # implementation in a worker avoids blocking this event loop.
    return await asyncio.to_thread(fetch_treasury_risk_free_rate_sync)


def fetch_treasury_risk_free_rate_sync() -> float:
    """Synchronous 10Y Treasury fetch for request handlers."""
    with _risk_free_lock:
        if monotonic() - _risk_free_cache_updated_at < RISK_FREE_CACHE_TTL_SECONDS:
            return GLOBAL_RISK_FREE_RATE

    with _risk_free_refresh_lock:
        # Double-check after waiting: another caller may have refreshed it.
        with _risk_free_lock:
            if monotonic() - _risk_free_cache_updated_at < RISK_FREE_CACHE_TTL_SECONDS:
                return GLOBAL_RISK_FREE_RATE

        current_year = datetime.now(timezone.utc).year
        try:
            with httpx.Client(headers={"User-Agent": TREASURY_USER_AGENT}) as client:
                for year in (current_year, current_year - 1):
                    response = client.get(
                        TREASURY_YIELD_CURVE_XML_URL,
                        params=_treasury_xml_params(year),
                        timeout=TREASURY_REQUEST_TIMEOUT_SECONDS,
                    )
                    response.raise_for_status()
                    parsed = _parse_latest_10y_from_xml(response.text)
                    if parsed is not None:
                        rate, as_of = parsed
                        return _store_risk_free_rate(
                            rate,
                            as_of,
                            "U.S. Treasury Daily Treasury Par Yield Curve Rates",
                        )
        except Exception as exc:
            logger.error(
                "treasury_risk_free_rate_fetch_failed",
                extra={"error_type": type(exc).__name__},
            )
        stale_rate = _load_disk_cached_risk_free_rate()
        if stale_rate is not None:
            return stale_rate
        return GLOBAL_RISK_FREE_RATE

def get_risk_free_rate() -> float:
    """Return the cached risk-free rate."""
    return GLOBAL_RISK_FREE_RATE


def get_risk_free_rate_metadata() -> dict:
    """Return source metadata for the cached risk-free rate."""
    return {
        "risk_free_rate": GLOBAL_RISK_FREE_RATE,
        "risk_free_rate_as_of": GLOBAL_RISK_FREE_AS_OF,
        "risk_free_rate_source": GLOBAL_RISK_FREE_SOURCE,
    }

def calculate_cost_of_equity(beta: float, risk_free_rate: float = None, market_risk_premium: float = 0.055, country_risk_premium: float = 0.0) -> float:
    """Calculate Cost of Equity (K_e) using CAPM with Blume's Adjusted Beta."""
    if risk_free_rate is None:
        risk_free_rate = get_risk_free_rate()
        
    adjusted_beta = (2.0 / 3.0 * beta) + (1.0 / 3.0 * 1.0)
    if country_risk_premium < 0:
        raise ValueError("Country risk premium cannot be negative.")
    coe = risk_free_rate + (adjusted_beta * market_risk_premium) + country_risk_premium
    
    MAX_COE = 0.125
    if coe > MAX_COE:
        logger.warning(f"Calculated COE {coe:.4f} exceeds {MAX_COE:.4f}, capping.")
        coe = MAX_COE
        
    return coe

def calculate_wacc(
    market_value_equity: float,
    total_debt: float,
    cost_of_equity: float,
    interest_expense: float,
    pretax_income: float,
    income_tax_expense: float
) -> float:
    """Calculate Weighted Average Cost of Capital (WACC)."""
    total_capital = market_value_equity + total_debt
    if total_capital == 0:
        return cost_of_equity
        
    weight_equity = market_value_equity / total_capital
    weight_debt = total_debt / total_capital
    
    cost_of_debt = 0.0
    if total_debt > 0:
        cost_of_debt = abs(interest_expense) / total_debt
        
    tax_rate = 0.0
    if pretax_income > 0:
        tax_rate = abs(income_tax_expense) / pretax_income
        
    return (weight_equity * cost_of_equity) + (weight_debt * cost_of_debt * (1 - tax_rate))
