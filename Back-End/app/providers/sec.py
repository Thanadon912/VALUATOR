from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from app.providers.base import ProviderResult, ProviderSource
from app.providers.sec_capital_allocation import extract_capital_allocation
from app.providers.sec_customer_mix_ai import (
    extract_customer_mix_with_fallback,
)
from app.providers.sec_debt_share_analysis import extract_debt_share_analysis
from app.providers.sec_financials import extract_financial_statements
from app.providers.sec_revenue_mix import (
    extract_revenue_mix_from_companyfacts,
    extract_revenue_mix_from_inline_xbrl,
)
from app.providers.sec_supply_chain_ai import extract_supply_chain_with_fallback
from app.providers.finnhub_metrics import fetch_finnhub_metrics


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
)
TICKER_CACHE_TTL_SECONDS = 24 * 60 * 60
# Bucket A — Fundamental & Structural Cache.
# Company Facts (financial statements, SIC, DEI share counts) are point-in-time
# SEC filings that only change on the next 10-Q/10-K. A 14-day in-memory cache
# serves fast structural re-entry on tab swap without serving stale live data.
COMPANY_CACHE_TTL_SECONDS = 14 * 24 * 60 * 60

_cache_lock = Lock()
_ticker_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
_company_cache: dict[str, tuple[float, ProviderResult]] = {}
_company_fetch_locks_guard = Lock()
_company_fetch_locks: dict[str, Lock] = {}
_ticker_fetch_lock = Lock()


def _company_fetch_lock(ticker: str) -> Lock:
    with _company_fetch_locks_guard:
        return _company_fetch_locks.setdefault(ticker, Lock())

US_GAAP_ANNUAL_CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_expenditure": [
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForProceedsFromOtherPropertyPlantAndEquipment",
    ],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "operating_income": ["OperatingIncomeLoss"],
    "research_development": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentInProcess",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        "Depreciation",
    ],
    "dividends_per_share": [
        "CommonStockDividendsPerShareDeclared",
        "CommonStockDividendsPerShareCashPaid",
    ],
}

US_GAAP_INSTANT_CONCEPTS = {
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndDueFromBanks",
    ],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "debt_current": ["ShortTermBorrowings", "LongTermDebtCurrent"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "total_debt": [
        "DebtCurrentAndNoncurrent",
        "DebtAndFinanceLeaseObligations",
        "LongTermDebtAndFinanceLeaseObligations",
    ],
    "shares": ["EntityCommonStockSharesOutstanding"],
}

US_GAAP_REGULATORY_CAPITAL_CONCEPTS = {
    "tier1_capital_ratio": [
        "Tier1CapitalRatio",
        "TierOneCapitalRatio",
        "Tier1RiskBasedCapitalRatio",
        "TierOneRiskBasedCapitalRatio",
        "RegulatoryCapitalTierOneCapitalRatio",
        "CommonEquityTier1CapitalRatio",
    ],
    "tier1_capital": [
        "Tier1Capital",
        "TierOneCapital",
        "RegulatoryCapitalTierOneCapital",
        "CommonEquityTier1Capital",
    ],
}

IFRS_ANNUAL_CONCEPTS = {
    "revenue": ["Revenue"],
    "net_income": [
        "ProfitLossAttributableToOwnersOfParent",
        "ProfitLoss",
    ],
    "operating_cash_flow": ["CashFlowsFromUsedInOperatingActivities"],
    "capital_expenditure": [
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "PurchaseOfPropertyPlantAndEquipment",
        "PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssetsOtherThanGoodwill",
    ],
    "eps": [
        "DilutedEarningsLossPerShare",
        "BasicEarningsLossPerShare",
    ],
    "operating_income": ["ProfitLossFromOperatingActivities"],
    "research_development": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentCostsRecognisedAsExpense",
        "ResearchAndDevelopmentExpenseByNature",
        "ResearchExpense",
        "DevelopmentExpense",
    ],
    "depreciation_amortization": [
        "DepreciationExpense",
        "DepreciationAndAmortisationExpense",
    ],
    "dividends_per_share": [
        "DividendsRecognisedAsDistributionsToOwnersPerShare",
    ],
}

IFRS_INSTANT_CONCEPTS = {
    "cash": ["CashAndCashEquivalents"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "EquityAttributableToOwnersOfParent",
        "Equity",
    ],
    "debt_current": [
        "CurrentPortionOfLongtermBorrowings",
        "CurrentBorrowings",
    ],
    "debt_noncurrent": [
        "LongtermBorrowings",
        "NoncurrentBorrowings",
    ],
    "total_debt": ["Borrowings", "LeaseLiabilities"],
    "shares": ["EntityCommonStockSharesOutstanding"],
}

# Backward-compatible aliases used by existing normalization tests and imports.
ANNUAL_CONCEPTS = US_GAAP_ANNUAL_CONCEPTS
INSTANT_CONCEPTS = US_GAAP_INSTANT_CONCEPTS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ticker_aliases(ticker: str) -> set[str]:
    return {ticker, ticker.replace(".", "-"), ticker.replace("-", ".")}


def _units_for_concept(
    facts: dict[str, Any],
    concepts: list[str],
    preferred_units: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    best_concept = None
    best_unit = None
    best_units_list = []
    latest_date = ""

    for concept in concepts:
        payload = facts.get(concept)
        if not payload:
            continue
        units = payload.get("units", {})
        for unit in preferred_units:
            if unit in units:
                # Find the latest date for this concept
                concept_latest = ""
                for fact in units[unit]:
                    fact_date = fact.get("end") or ""
                    if fact_date > concept_latest:
                        concept_latest = fact_date
                
                if concept_latest > latest_date:
                    latest_date = concept_latest
                    best_concept = concept
                    best_unit = unit
                    best_units_list = units[unit]
                break
        else:
            if units and not best_unit:
                unit = list(units.keys())[0]
                concept_latest = ""
                for fact in units[unit]:
                    fact_date = fact.get("end") or ""
                    if fact_date > concept_latest:
                        concept_latest = fact_date
                
                if concept_latest > latest_date:
                    latest_date = concept_latest
                    best_concept = concept
                    best_unit = unit
                    best_units_list = units[unit]

    if best_concept:
        return best_units_list, best_concept, best_unit
        
    return [], None, None


def _annual_series(
    facts: dict[str, Any],
    concepts: list[str],
    preferred_units: tuple[str, ...] = ("USD", "USD/shares", "pure"),
    limit: int = 5,
) -> list[dict[str, Any]]:
    units, concept, unit = _units_for_concept(facts, concepts, preferred_units)
    by_end: dict[str, dict[str, Any]] = {}

    for fact in units:
        if fact.get("form") not in {"10-K", "20-F", "40-F"}:
            continue
        if fact.get("fp") != "FY" or not fact.get("start") or not fact.get("end"):
            continue
        if not _is_comparable_annual_duration(fact):
            continue
        existing = by_end.get(fact["end"])
        if existing is None or fact.get("filed", "") > existing.get("filed", ""):
            by_end[fact["end"]] = fact

    rows = sorted(by_end.values(), key=lambda item: item["end"])[-limit:]
    return [
        {
            "period": row["end"][:4],
            "start": row.get("start"),
            "end": row["end"],
            "value": row["val"],
            "unit": unit,
            "concept": concept,
            "form": row.get("form"),
            "filed": row.get("filed"),
            "accession": row.get("accn"),
        }
        for row in rows
    ]


def _annual_series_across_concepts(
    facts: dict[str, Any],
    concepts: list[str],
    preferred_units: tuple[str, ...] = ("USD",),
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Build one comparable annual series across renamed synonymous concepts."""
    available = [
        (concept, facts[concept].get("units", {}))
        for concept in concepts
        if concept in facts
    ]
    selected_unit = next(
        (unit for unit in preferred_units if any(unit in units for _, units in available)),
        None,
    )
    if selected_unit is None:
        selected_unit = next(
            (unit for _, units in available for unit in units if len(unit) == 3 and unit.isupper()),
            None,
        )
    if selected_unit is None:
        return []

    by_end: dict[str, tuple[dict[str, Any], str]] = {}
    for concept, units in available:
        for fact in units.get(selected_unit, []):
            if fact.get("form") not in {"10-K", "20-F", "40-F"}:
                continue
            if fact.get("fp") != "FY" or not fact.get("start") or not fact.get("end"):
                continue
            if not _is_comparable_annual_duration(fact):
                continue
            existing = by_end.get(fact["end"])
            if existing is None or fact.get("filed", "") > existing[0].get("filed", ""):
                by_end[fact["end"]] = (fact, concept)

    rows = sorted(by_end.values(), key=lambda item: item[0]["end"])[-limit:]
    return [
        {
            "period": row["end"][:4], "start": row.get("start"), "end": row["end"],
            "value": row["val"], "unit": selected_unit, "concept": concept,
            "form": row.get("form"), "filed": row.get("filed"), "accession": row.get("accn"),
        }
        for row, concept in rows
    ]


def _is_comparable_annual_duration(fact: dict[str, Any]) -> bool:
    """Reject quarter/YTD facts that SEC filings sometimes label as FY."""
    try:
        start = datetime.fromisoformat(str(fact["start"])).date()
        end = datetime.fromisoformat(str(fact["end"])).date()
    except (KeyError, TypeError, ValueError):
        return False
    duration_days = (end - start).days
    return 300 <= duration_days <= 430


def _quarterly_series(
    facts: dict[str, Any],
    concepts: list[str],
    preferred_units: tuple[str, ...],
    limit: int = 4,
) -> list[dict[str, Any]]:
    units, concept, unit = _units_for_concept(facts, concepts, preferred_units)
    by_frame: dict[str, dict[str, Any]] = {}

    for fact in units:
        frame = fact.get("frame", "")
        if fact.get("form") not in {"10-Q", "10-K", "20-F", "40-F", "6-K"}:
            continue
        if not frame.startswith("CY") or "Q" not in frame or fact.get("start") is None:
            continue
        existing = by_frame.get(frame)
        if existing is None or fact.get("filed", "") > existing.get("filed", ""):
            by_frame[frame] = fact

    rows = sorted(by_frame.items(), key=lambda item: item[0])[-limit:]
    return [
        {
            "period": frame.replace("CY", ""),
            "start": row.get("start"),
            "end": row.get("end"),
            "value": row["val"],
            "unit": unit,
            "concept": concept,
            "form": row.get("form"),
            "filed": row.get("filed"),
            "accession": row.get("accn"),
        }
        for frame, row in rows
    ]


def _latest_instant(
    facts: dict[str, Any],
    concepts: list[str],
    preferred_units: tuple[str, ...] = ("USD", "shares", "pure"),
) -> dict[str, Any] | None:
    units, concept, unit = _units_for_concept(facts, concepts, preferred_units)
    candidates = [
        fact
        for fact in units
        if fact.get("form") in {"10-Q", "10-K", "20-F", "40-F", "6-K"}
        and fact.get("end")
        and not fact.get("start")
    ]
    if not candidates:
        return None
    row = max(candidates, key=lambda item: (item["end"], item.get("filed", "")))
    return {
        "period": row["end"],
        "value": row["val"],
        "unit": unit,
        "concept": concept,
        "form": row.get("form"),
        "filed": row.get("filed"),
        "accession": row.get("accn"),
    }


def _resolve_common_shares_outstanding(
    all_facts: dict[str, Any],
    financial_facts: dict[str, Any],
    dei_facts: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve aggregate common shares, summing class facts only as a fallback."""
    direct_sources = (
        (dei_facts, ["EntityCommonStockSharesOutstanding"]),
        (financial_facts, ["CommonStockSharesOutstanding"]),
    )
    for facts, concepts in direct_sources:
        direct = _latest_instant(facts, concepts, ("shares",))
        if direct is not None and _fact_value(direct) and _fact_value(direct) > 0:
            direct["status"] = "reported"
            direct["basis"] = f"aggregate SEC fact: {direct['concept']}"
            direct["input_refs"] = [direct["concept"]]
            return direct

    class_rows: list[dict[str, Any]] = []
    excluded_terms = ("preferred", "weightedaverage", "option", "award")
    for taxonomy, taxonomy_facts in all_facts.items():
        for concept in taxonomy_facts:
            normalized = concept.lower()
            if "sharesoutstanding" not in normalized or "commonstock" not in normalized:
                continue
            if any(term in normalized for term in excluded_terms):
                continue
            row = _latest_instant(taxonomy_facts, [concept], ("shares",))
            value = _fact_value(row)
            if row is not None and value is not None and value > 0:
                row["taxonomy"] = taxonomy
                class_rows.append(row)

    if len(class_rows) < 2:
        return None
    latest_period = max(row["period"] for row in class_rows)
    matching = [row for row in class_rows if row["period"] == latest_period]
    if len(matching) < 2:
        return None
    accessions = {row.get("accession") for row in matching if row.get("accession")}
    if len(accessions) > 1:
        return None
    return {
        "period": latest_period,
        "value": sum(_fact_value(row) or 0.0 for row in matching),
        "unit": "shares",
        "concept": None,
        "form": matching[0].get("form"),
        "filed": max(row.get("filed") or "" for row in matching),
        "accession": next(iter(accessions), None),
        "status": "derived",
        "basis": "sum of SEC common voting/non-voting share-class facts for matching period",
        "input_refs": [
            f"{row['taxonomy']}:{row['concept']}" for row in matching
        ],
    }


def _latest_fact(
    facts: dict[str, Any],
    concepts: list[str],
    preferred_units: tuple[str, ...] = ("pure", "percent", "USD"),
) -> dict[str, Any] | None:
    units, concept, unit = _units_for_concept(facts, concepts, preferred_units)
    candidates = [
        fact
        for fact in units
        if fact.get("form") in {"10-Q", "10-K", "20-F", "40-F", "6-K"}
        and fact.get("end")
    ]
    if not candidates:
        return None
    row = max(candidates, key=lambda item: (item["end"], item.get("filed", "")))
    return {
        "period": row["end"],
        "start": row.get("start"),
        "end": row["end"],
        "value": row.get("val"),
        "unit": unit,
        "concept": concept,
        "form": row.get("form"),
        "filed": row.get("filed"),
        "accession": row.get("accn"),
    }


def _fact_value(fact: dict[str, Any] | None) -> float | None:
    if fact is None:
        return None
    value = fact.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derive_total_debt_instant(
    instants: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    reported_total = instants.get("total_debt")
    if reported_total is not None:
        return reported_total

    current = instants.get("debt_current")
    noncurrent = instants.get("debt_noncurrent")
    current_value = _fact_value(current)
    noncurrent_value = _fact_value(noncurrent)
    if current_value is None or noncurrent_value is None:
        return None
    if current.get("unit") != noncurrent.get("unit"):
        return None
    if current.get("period") != noncurrent.get("period"):
        return None
    return {
        "period": current.get("period"),
        "value": current_value + noncurrent_value,
        "unit": current.get("unit"),
        "concept": None,
        "form": current.get("form"),
        "filed": max(current.get("filed") or "", noncurrent.get("filed") or ""),
        "accession": current.get("accession"),
        "status": "derived",
        "basis": "debt_current + debt_noncurrent using matching SEC period and unit",
        "input_refs": [
            current.get("concept") or "debt_current",
            noncurrent.get("concept") or "debt_noncurrent",
        ],
    }


def _margin_history(
    operating_income: list[dict[str, Any]],
    revenue: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    revenue_by_end = {
        row.get("end") or row.get("period"): row
        for row in revenue
        if row.get("value") is not None
    }
    rows: list[dict[str, Any]] = []
    for operating_row in operating_income:
        period = operating_row.get("end") or operating_row.get("period")
        revenue_row = revenue_by_end.get(period)
        if revenue_row is None:
            continue
        operating_value = _fact_value(operating_row)
        revenue_value = _fact_value(revenue_row)
        if operating_value is None or revenue_value is None or revenue_value <= 0:
            continue
        if operating_row.get("unit") != revenue_row.get("unit"):
            continue
        rows.append(
            {
                "period": operating_row.get("period"),
                "start": operating_row.get("start"),
                "end": operating_row.get("end"),
                "value": operating_value / revenue_value,
                "unit": "ratio",
                "basis": "operating_income / revenue",
                "input_refs": [
                    operating_row.get("concept") or "operating_income",
                    revenue_row.get("concept") or "revenue",
                ],
            }
        )
    return rows[-limit:]


def _adaptive_valuation_data(
    *,
    profile: dict[str, Any],
    financial_facts: dict[str, Any],
    annual_concepts: dict[str, list[str]],
    instants: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    revenue_history = _annual_series(
        financial_facts,
        annual_concepts.get("revenue", []),
        limit=10,
    )
    operating_income_history = _annual_series(
        financial_facts,
        annual_concepts.get("operating_income", []),
        limit=10,
    )
    r_and_d_history = _annual_series_across_concepts(
        financial_facts,
        annual_concepts.get("research_development", []),
        limit=10,
    )
    net_income_history = _annual_series(
        financial_facts,
        annual_concepts.get("net_income", []),
        limit=10,
    )
    capex_history = _annual_series(
        financial_facts,
        annual_concepts.get("capital_expenditure", []),
        limit=10,
    )
    regulatory_capital = {
        name: _latest_fact(financial_facts, concepts)
        for name, concepts in US_GAAP_REGULATORY_CAPITAL_CONCEPTS.items()
    }
    return {
        "sic_code": profile.get("sic"),
        "sic_description": profile.get("sic_description"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry") or profile.get("sic_description"),
        "revenue_history": revenue_history,
        "r_and_d_history": r_and_d_history,
        "net_income_history": net_income_history,
        "regulatory_capital": regulatory_capital,
        "capex_history": capex_history,
        "total_debt": _derive_total_debt_instant(instants),
        "cash_and_cash_equivalents": instants.get("cash"),
        "operating_income_history": operating_income_history,
        "operating_margin_history": _margin_history(
            operating_income_history,
            revenue_history,
            limit=10,
        ),
    }


def _select_financial_taxonomy(
    all_facts: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    us_gaap = all_facts.get("us-gaap", {})
    ifrs = all_facts.get("ifrs-full", {})
    if us_gaap:
        return (
            "us-gaap",
            us_gaap,
            US_GAAP_ANNUAL_CONCEPTS,
            US_GAAP_INSTANT_CONCEPTS,
        )
    if ifrs:
        return (
            "ifrs-full",
            ifrs,
            IFRS_ANNUAL_CONCEPTS,
            IFRS_INSTANT_CONCEPTS,
        )
    return (
        "unavailable",
        {},
        US_GAAP_ANNUAL_CONCEPTS,
        US_GAAP_INSTANT_CONCEPTS,
    )


def _latest_annual_filing(submissions: dict[str, Any]) -> dict[str, str] | None:
    return _latest_filing(submissions, {"10-K", "20-F", "40-F"})


def _latest_quarterly_filing(
    submissions: dict[str, Any],
) -> dict[str, str] | None:
    return _latest_filing(submissions, {"10-Q", "6-K"})


def _latest_filing(
    submissions: dict[str, Any],
    accepted_forms: set[str],
) -> dict[str, str] | None:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []

    def value_at(field: str, index: int) -> str:
        values = recent.get(field) or []
        return values[index] if index < len(values) else ""

    for index, form in enumerate(forms):
        if form not in accepted_forms:
            continue
        accession = value_at("accessionNumber", index)
        document = value_at("primaryDocument", index)
        if not accession or not document:
            return None
        return {
            "form": form,
            "accession": accession,
            "document": document,
            "report_date": value_at("reportDate", index),
            "filing_date": value_at("filingDate", index),
        }
    return None


class SecCompanyFactsProvider:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 8,
        supply_chain_ai_enabled: bool = False,
        gemini_api_key: str | None = None,
        gemini_supply_chain_model: str = "gemini-3.1-flash-lite",
        supply_chain_cache_dir: str | None = None,
        customer_mix_ai_enabled: bool = False,
        gemini_customer_mix_primary_model: str = "gemini-3.1-flash-lite",
        gemini_customer_mix_secondary_model: str = "gemini-2.5-flash-lite",
        customer_mix_ai_rate_limit_cooldown_seconds: float = 300,
        customer_mix_cache_dir: str | None = None,
    ) -> None:
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self.timeout_seconds = timeout_seconds
        self.supply_chain_ai_enabled = supply_chain_ai_enabled
        self.gemini_api_key = gemini_api_key
        self.gemini_supply_chain_model = gemini_supply_chain_model
        self.supply_chain_cache_dir = supply_chain_cache_dir
        self.customer_mix_ai_enabled = customer_mix_ai_enabled
        self.gemini_customer_mix_primary_model = (
            gemini_customer_mix_primary_model
        )
        self.gemini_customer_mix_secondary_model = (
            gemini_customer_mix_secondary_model
        )
        self.customer_mix_ai_rate_limit_cooldown_seconds = (
            customer_mix_ai_rate_limit_cooldown_seconds
        )
        self.customer_mix_cache_dir = customer_mix_cache_dir

    def fetch(self, ticker: str) -> ProviderResult:
        normalized = ticker.strip().upper()
        with _cache_lock:
            cached = _company_cache.get(normalized)
            if cached and monotonic() - cached[0] < COMPANY_CACHE_TTL_SECONDS:
                return cached[1]

        # One SEC refresh per company process-wide. This also covers callers
        # running in independent asyncio event loops.
        with _company_fetch_lock(normalized):
            with _cache_lock:
                cached = _company_cache.get(normalized)
                if cached and monotonic() - cached[0] < COMPANY_CACHE_TTL_SECONDS:
                    return cached[1]
            return self._fetch_uncached(normalized)

    def _fetch_uncached(self, ticker: str) -> ProviderResult:
        fetched_at = _utc_now()
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                global _ticker_cache
                with _cache_lock:
                    cached_tickers = _ticker_cache
                if cached_tickers is None or monotonic() - cached_tickers[0] >= TICKER_CACHE_TTL_SECONDS:
                    # Different tickers share this mapping. Guard its refresh
                    # separately so a cold burst downloads it only once.
                    with _ticker_fetch_lock:
                        with _cache_lock:
                            cached_tickers = _ticker_cache
                        if (
                            cached_tickers is None
                            or monotonic() - cached_tickers[0] >= TICKER_CACHE_TTL_SECONDS
                        ):
                            ticker_response = client.get(SEC_TICKERS_URL)
                            ticker_response.raise_for_status()
                            ticker_payload = ticker_response.json()
                            with _cache_lock:
                                _ticker_cache = (monotonic(), ticker_payload)
                        else:
                            ticker_payload = cached_tickers[1]
                else:
                    ticker_payload = cached_tickers[1]

                ticker_rows = ticker_payload.values()
                aliases = _ticker_aliases(ticker)
                company = next(
                    (
                        row
                        for row in ticker_rows
                        if str(row.get("ticker", "")).upper() in aliases
                    ),
                    None,
                )
                if company is None:
                    result = ProviderResult(
                        data=None,
                        warnings=[f"SEC does not list {ticker} in its ticker mapping."],
                    )
                    with _cache_lock:
                        _company_cache[ticker] = (monotonic(), result)
                    return result

                cik = f"{int(company['cik_str']):010d}"
                facts_url = SEC_COMPANY_FACTS_URL.format(cik=cik)
                submissions_url = SEC_SUBMISSIONS_URL.format(cik=cik)
                facts_response = client.get(facts_url)
                facts_response.raise_for_status()
                payload = facts_response.json()
                submissions_response = client.get(submissions_url)
                submissions_response.raise_for_status()
                submissions = submissions_response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return ProviderResult(
                data=None,
                warnings=[f"SEC provider request failed: {exc.__class__.__name__}."],
            )

        all_facts = payload.get("facts", {})
        dei = payload.get("facts", {}).get("dei", {})
        (
            taxonomy,
            financial_facts,
            annual_concepts,
            instant_concepts,
        ) = _select_financial_taxonomy(all_facts)

        annual = {
            name: _annual_series(financial_facts, concepts)
            for name, concepts in annual_concepts.items()
        }
        instants = {
            name: _latest_instant(
                dei if name == "shares" else financial_facts,
                concepts,
            )
            for name, concepts in instant_concepts.items()
        }
        instants["shares"] = _resolve_common_shares_outstanding(
            all_facts,
            financial_facts,
            dei,
        )
        quarterly_eps = _quarterly_series(
            financial_facts,
            annual_concepts["eps"],
            ("USD/shares", "pure"),
        )
        revenue_mix = extract_revenue_mix_from_companyfacts(
            ticker,
            payload,
            annual.get("revenue", []),
            source_url=facts_url,
        )
        revenue_mix_source_index = 0 if revenue_mix else None
        filing_sources: list[ProviderSource] = []
        filing_documents: list[dict[str, str]] = []
        filing_warnings: list[str] = []
        selected_filings = [
            filing
            for filing in (
                _latest_annual_filing(submissions),
                _latest_quarterly_filing(submissions),
            )
            if filing is not None
        ]
        for filing in selected_filings:
            filing_url = SEC_FILING_URL.format(
                cik=int(cik),
                accession=filing["accession"].replace("-", ""),
                document=filing["document"],
            )
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    headers=self.headers,
                    follow_redirects=True,
                ) as client:
                    filing_response = client.get(filing_url)
                    filing_response.raise_for_status()
                filing_documents.append(
                    {
                        **filing,
                        "source_url": filing_url,
                        "html": filing_response.text,
                    }
                )
                filing_sources.append(
                    ProviderSource(
                        provider=f"SEC EDGAR {filing['form']}",
                        source_url=filing_url,
                        source_timestamp=filing.get("filing_date") or None,
                        fetched_at=fetched_at,
                    )
                )
            except (httpx.HTTPError, ValueError) as exc:
                filing_warnings.append(
                    f"SEC {filing['form']} filing request failed: "
                    f"{exc.__class__.__name__}."
                )
                continue

        if not revenue_mix:
            annual_document = next(
                (
                    document
                    for document in filing_documents
                    if document["form"] in {"10-K", "20-F", "40-F"}
                ),
                None,
            )
            if annual_document is not None:
                revenue_mix = extract_revenue_mix_from_inline_xbrl(
                    ticker,
                    annual_document["html"],
                    annual.get("revenue", []),
                    filing_url=annual_document["source_url"],
                    filing_date=annual_document.get("filing_date"),
                )
                if revenue_mix:
                    annual_accession = annual_document["accession"]
                    filing_offset = next(
                        (
                            index
                            for index, document in enumerate(filing_documents)
                            if document["accession"] == annual_accession
                        ),
                        None,
                    )
                    if filing_offset is not None:
                        revenue_mix_source_index = 2 + filing_offset

        supply_chain, supply_chain_warning = extract_supply_chain_with_fallback(
            ticker,
            filing_documents,
            enabled=self.supply_chain_ai_enabled,
            api_key=self.gemini_api_key,
            model=self.gemini_supply_chain_model,
            timeout_seconds=self.timeout_seconds,
            cache_dir=self.supply_chain_cache_dir,
        )
        if supply_chain_warning:
            filing_warnings.append(supply_chain_warning)
        customer_mix, customer_mix_warning = (
            extract_customer_mix_with_fallback(
                ticker,
                filing_documents,
                enabled=self.customer_mix_ai_enabled,
                api_key=self.gemini_api_key,
                primary_model=self.gemini_customer_mix_primary_model,
                secondary_model=self.gemini_customer_mix_secondary_model,
                timeout_seconds=self.timeout_seconds,
                rate_limit_cooldown_seconds=(
                    self.customer_mix_ai_rate_limit_cooldown_seconds
                ),
                cache_dir=self.customer_mix_cache_dir,
            )
        )
        if customer_mix_warning:
            filing_warnings.append(customer_mix_warning)
        sic = submissions.get("sic") or ""
        sic_desc = (submissions.get("sicDescription") or "").lower()
        is_bank = str(sic).startswith("60") or "bank" in sic_desc or "financial services" in sic_desc
        profile = {
            "sic": submissions.get("sic"),
            "sic_description": submissions.get("sicDescription"),
            "exchange": next(
                iter(submissions.get("exchanges") or []),
                None,
            ),
            "fiscal_year_end": submissions.get("fiscalYearEnd"),
            "state_of_incorporation": submissions.get("stateOfIncorporation"),
            "entity_type": submissions.get("entityType"),
            "filer_category": submissions.get("category"),
            "phone": submissions.get("phone"),
            "business_address": submissions.get("addresses", {}).get("business"),
            "former_names": submissions.get("formerNames") or [],
        }

        capital_allocation = extract_capital_allocation(
            ticker,
            payload,
            filing_documents,
            cik=cik,
        )
        financial_statements = extract_financial_statements(payload, is_bank=is_bank)
        profile["reported_currency"] = (
            financial_statements.get("annual", {}).get("income", {}).get("currency")
            or financial_statements.get("annual", {}).get("balance_sheet", {}).get("currency")
        )
        profile["is_foreign_private_issuer"] = any(
            filing.get("form") in {"20-F", "40-F", "6-K"} for filing in selected_filings
        )
        profile["adr_ratio"] = None if profile["is_foreign_private_issuer"] else 1.0
        profile["adr_ratio_source"] = None if profile["is_foreign_private_issuer"] else "not an FPI; ordinary share basis"
        
        debt_share_analysis = extract_debt_share_analysis(
            ticker,
            financial_statements,
            capital_allocation,
            filing_documents,
            cik=cik,
            companyfacts=payload,
            is_bank=is_bank,
        )
        adaptive_valuation_data = _adaptive_valuation_data(
            profile=profile,
            financial_facts=financial_facts,
            annual_concepts=annual_concepts,
            instants=instants,
        )

        latest_filed_dates = [
            row["filed"]
            for series in annual.values()
            for row in series
            if row.get("filed")
        ]
        latest_filed_dates.extend(
            row["filed"] for row in quarterly_eps if row.get("filed")
        )
        latest_filed_dates.extend(
            row["filed"]
            for row in instants.values()
            if row is not None and row.get("filed")
        )
        source_timestamp = max(latest_filed_dates, default=None)

        sources = [
            ProviderSource(
                provider="SEC EDGAR",
                source_url=facts_url,
                source_timestamp=source_timestamp,
                fetched_at=fetched_at,
            ),
            ProviderSource(
                provider="SEC EDGAR Submissions",
                source_url=submissions_url,
                source_timestamp=source_timestamp,
                fetched_at=fetched_at,
            ),
        ]
        sources.extend(filing_sources)

        result = ProviderResult(
            data={
                "cik": cik,
                "taxonomy": taxonomy,
                "security_basis_compatible": taxonomy == "us-gaap",
                "company_name": (
                    submissions.get("name")
                    or payload.get("entityName")
                    or company.get("title")
                ),
                "profile": profile,
                "adaptive_valuation_data": adaptive_valuation_data,
                "annual": annual,
                "quarterly_eps": quarterly_eps,
                "instants": instants,
                "revenue_mix": revenue_mix,
                "revenue_mix_source_index": revenue_mix_source_index,
                "supply_chain": supply_chain,
                "supply_chain_source_indexes": list(
                    range(2, 2 + len(filing_sources))
                ),
                "customer_mix": customer_mix,
                "customer_mix_source_indexes": list(
                    range(2, 2 + len(filing_sources))
                ),
                "capital_allocation": capital_allocation,
                "capital_allocation_source_indexes": list(
                    range(2, 2 + len(filing_sources))
                ),
                "financial_statements": financial_statements,
                "debt_share_analysis": debt_share_analysis,
                "debt_share_analysis_source_indexes": list(
                    range(2, 2 + len(filing_sources))
                ),
            },
            sources=sources,
            warnings=filing_warnings,
        )
        with _cache_lock:
            _company_cache[ticker] = (monotonic(), result)
        return result
