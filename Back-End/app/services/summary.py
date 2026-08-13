from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

from app.core.config import get_settings
from app.models import SourceRecord, SummaryData, SummaryModule, SummaryResponse
from app.providers.base import ProviderResult
from app.providers.nasdaq import NasdaqMarketProvider
from app.providers.unified_financials import get_unified_financials_sync
from app.providers.finnhub_metrics import FinnhubMetricProvider


def _instant_value(instants: dict[str, Any], key: str) -> Any:
    """Return an instant fact value while tolerating explicit null facts."""
    fact = instants.get(key) or {}
    return fact.get("value")


def _get_mrq(financials: dict, stmt: str, row_id: str):
    def _fetch_from_period(period_name: str):
        period_data = financials.get(period_name, {})
        stmt_data = period_data.get(stmt, {})
        rows = stmt_data.get("rows", [])
        row = next((r for r in rows if r["id"] == row_id), None)
        if not row:
            return None
        cells = row.get("cells", {})
        valid_dates = [k for k, v in cells.items() if v.get("value") is not None]
        if not valid_dates:
            return None
        valid_dates.sort()
        latest_date = valid_dates[-1]
        return cells[latest_date]["value"]

    val = _fetch_from_period("quarterly")
    if val is None:
        val = _fetch_from_period("annual")
    return val

def _get_ttm(financials: dict, stmt: str, row_id: str):
    quarterly = financials.get("quarterly", {})
    stmt_data = quarterly.get(stmt, {})
    rows = stmt_data.get("rows", [])
    row = next((r for r in rows if r["id"] == row_id), None)
    cells = row.get("cells", {}) if row else {}
    valid_dates = [k for k, v in cells.items() if v.get("value") is not None]

    ttm_keys = [k for k in valid_dates if k.startswith("TTM_")]
    if ttm_keys:
        ttm_keys.sort()
        return cells[ttm_keys[-1]]["value"]

    quarterly_dates = [k for k in valid_dates if not k.startswith("TTM_")]
    if not quarterly_dates or len(quarterly_dates) < 4:
        # Fallback to latest annual if we don't have 4 quarters
        annual_data = financials.get("annual", {}).get(stmt, {})
        a_rows = annual_data.get("rows", [])
        a_row = next((r for r in a_rows if r["id"] == row_id), None)
        if not a_row:
            return None
        a_cells = a_row.get("cells", {})
        a_valid = [k for k, v in a_cells.items() if v.get("value") is not None]
        if not a_valid:
            return None
        a_valid.sort()
        return a_cells[a_valid[-1]]["value"]
    
    quarterly_dates.sort()
    # sum last 4 quarters
    return sum([cells[date]["value"] for date in quarterly_dates[-4:]])

def _get_ttm_at_factory(financials: dict, date_key: str):
    def _get_ttm_at(stmt: str, row_id: str):
        rows = financials.get("quarterly", {}).get(stmt, {}).get("rows", [])
        row = next((r for r in rows if r["id"] == row_id), None)
        if not row:
            return None
        cells = row.get("cells", {})
        periods = financials.get("quarterly", {}).get(stmt, {}).get("periods", [])
        idx = -1
        for i, p in enumerate(periods):
            pe = p.get("period_end") or p["key"]
            if pe == date_key or p["key"] == date_key:
                idx = i
                break
            if pe <= date_key and idx == -1:
                idx = i
        if idx == -1 or idx + 3 >= len(periods):
            return None
        total = 0
        for i in range(idx, idx + 4):
            v = cells.get(periods[i]["key"], {}).get("value")
            if v is None:
                return None
            total += v
        return total
    return _get_ttm_at


MODULE_MESSAGES = {
    "quote": "No quote provider is configured.",
    "price_history": "Price history will appear after a market-data provider is connected.",
    "key_facts": "Key facts require normalized quote and statistics data.",
    "company_overview": "Company profile data is currently unavailable.",
    "revenue_mix": "No reliable reported revenue mix is available.",
    "supply_chain": "Supply-chain relationships require traceable source data.",
    "customer_mix": "No reliable SEC customer-mix disclosure is available.",
    "performance": "Performance comparisons require sourced market history.",
    "eps_trend": "EPS history and estimates are currently unavailable.",
    "revenue_earnings": "Revenue and earnings history is currently unavailable.",
    "valuation_measures": "Valuation measures require sourced market and statement data.",
    "financial_highlights": "Financial highlights require normalized financial statements.",
    "peer_comparison": "Peer comparison requires an approved, deterministic peer dataset.",
}


def unavailable_module(name: str) -> SummaryModule:
    return SummaryModule(
        status="unavailable",
        message=MODULE_MESSAGES[name],
        data=None,
        source_refs=[],
    )


def unavailable_revenue_mix(ticker: str) -> SummaryModule:
    return SummaryModule(
        status="unavailable",
        message=MODULE_MESSAGES["revenue_mix"],
        data={
            "ticker": ticker,
            "fiscal_year": None,
            "revenue_mix": {
                "business_segments": [],
                "products": [],
                "geography": [],
                "end_markets": [],
            },
            "periods": {
                "business_segments": [],
                "products": [],
                "geography": [],
                "end_markets": [],
            },
            "dimension_metadata": {},
        },
        source_refs=[],
    )


def unavailable_supply_chain(ticker: str) -> SummaryModule:
    return SummaryModule(
        status="unavailable",
        message=MODULE_MESSAGES["supply_chain"],
        data={
            "ticker": ticker,
            "fiscal_year": None,
            "extraction": {
                "method": "deterministic",
                "provider": None,
                "model": None,
                "extractor_version": None,
                "cache_source": None,
                "attempted_models": [],
                "model_failover_used": False,
                "model_failover_reason": None,
                "fallback_used": False,
                "fallback_reason": None,
            },
            "analyzed_filings": [],
            "supply_chain_exposure": {
                "suppliers": [],
                "manufacturing_locations": [],
                "raw_material_dependencies": [],
                "customer_concentrations": [],
                "risks": [],
            },
        },
        source_refs=[],
    )


def unavailable_customer_mix(ticker: str) -> SummaryModule:
    return SummaryModule(
        status="unavailable",
        message=MODULE_MESSAGES["customer_mix"],
        data={
            "ticker": ticker,
            "fiscal_year": None,
            "analyzed_filings": [],
            "customer_mix": {
                "major_customers": [],
                "customer_types": [],
                "channel_dependencies": [],
                "end_markets": [],
                "risks": [],
            },
        },
        source_refs=[],
    )


def _module(
    data: dict[str, Any] | None,
    message: str,
    source_refs: list[int],
    status: str = "success",
) -> SummaryModule:
    if data is None:
        return SummaryModule(
            status="unavailable",
            message=message,
            data=None,
            source_refs=[],
        )
    return SummaryModule(
        status=status,
        message=message,
        data=data,
        source_refs=source_refs,
    )


def _source_records(result: ProviderResult) -> list[SourceRecord]:
    return [
        SourceRecord(
            provider=source.provider,
            source_url=source.source_url,
            source_timestamp=source.source_timestamp,
            fetched_at=source.fetched_at,
            is_stale=source.is_stale,
        )
        for source in result.sources
    ]


def _latest(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    return series[-1] if series else None


def _period_label(fact: dict[str, Any]) -> str:
    return str(
        fact.get("period")
        or fact.get("end")
        or "latest reported period"
    )


def _safe_ratio(
    numerator: float | int | None,
    denominator: float | int | None,
) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return float(numerator) / float(denominator)


def _sum_required_values(
    *items: dict[str, Any] | None,
) -> float | int | None:
    if not items or any(item is None for item in items):
        return None
    reported = [item for item in items if item is not None]
    units = {item.get("unit") for item in reported}
    periods = {item.get("period") for item in reported}
    if len(units) != 1 or len(periods) != 1:
        return None
    return sum(item["value"] for item in reported)


def _same_period_ratio(
    numerator: dict[str, Any] | None,
    denominator: dict[str, Any] | None,
) -> float | None:
    if numerator is None or denominator is None:
        return None
    if numerator.get("unit") != denominator.get("unit"):
        return None
    numerator_period = numerator.get("end") or numerator.get("period")
    denominator_period = denominator.get("end") or denominator.get("period")
    if numerator_period != denominator_period:
        return None
    return _safe_ratio(numerator.get("value"), denominator.get("value"))


def _free_cash_flow_series(
    operating_cash_flow: list[dict[str, Any]],
    capital_expenditure: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    capex_by_end = {row["end"]: row for row in capital_expenditure}
    rows = []
    for cash_flow in operating_cash_flow:
        capex = capex_by_end.get(cash_flow["end"])
        if capex is None or capex.get("unit") != cash_flow.get("unit"):
            continue
        rows.append(
            {
                "period": cash_flow["period"],
                "end": cash_flow["end"],
                "value": cash_flow["value"] - abs(capex["value"]),
                "unit": cash_flow["unit"],
                "basis": "operating_cash_flow - capital_expenditure",
                "input_refs": [
                    cash_flow["concept"],
                    capex["concept"],
                ],
            }
        )
    return rows


def _performance(points: list[dict[str, Any]]) -> dict[str, float | None]:
    valid = [
        point
        for point in points
        if point.get("close") is not None and point.get("date")
    ]
    if not valid:
        return {"ytd": None, "one_year": None, "three_year": None, "five_year": None}

    latest = valid[-1]
    latest_date = date.fromisoformat(latest["date"])
    latest_close = latest["close"]

    def return_from(target: date) -> float | None:
        eligible = [
            point
            for point in valid
            if date.fromisoformat(point["date"]) <= target
        ]
        if not eligible:
            return None
        base = eligible[-1]["close"]
        if not base:
            return None
        return ((latest_close / base) - 1) * 100

    return {
        "ytd": return_from(date(latest_date.year - 1, 12, 31)),
        "one_year": return_from(latest_date - timedelta(days=365)),
        "three_year": return_from(latest_date - timedelta(days=365 * 3)),
        "five_year": return_from(latest_date - timedelta(days=365 * 5)),
    }


def _build_sec_modules(
    result: ProviderResult,
    source_refs: list[int],
    fh_metric_result: ProviderResult | None = None,
    market_result: ProviderResult | None = None,
) -> dict[str, SummaryModule]:
    if result.data is None:
        return {}

    annual = result.data["annual"]
    instants = result.data["instants"]
    base_source_refs = source_refs[:2]
    revenue = annual["revenue"]
    net_income = annual["net_income"]
    fcf = _free_cash_flow_series(
        annual["operating_cash_flow"],
        annual["capital_expenditure"],
    )
    latest_revenue = _latest(revenue)
    latest_income = _latest(net_income)
    latest_fcf = _latest(fcf)
    profile = result.data.get("profile", {})
    equity = instants.get("equity")
    debt_current = instants.get("debt_current")
    debt_noncurrent = instants.get("debt_noncurrent")
    total_debt = _sum_required_values(debt_current, debt_noncurrent)
    latest_equity = equity if equity and latest_income and (
        equity.get("period") == latest_income.get("end")
        and equity.get("unit") == latest_income.get("unit")
    ) else None

    earnings_by_end = {row["end"]: row for row in net_income}
    financial_trend = [
        {
            "period": row["period"],
            "end": row["end"],
            "revenue": row["value"],
            "earnings": earnings_by_end.get(row["end"], {}).get("value"),
            "currency": row["unit"],
        }
        for row in revenue
    ]
    fh_metrics = fh_metric_result.data if fh_metric_result and fh_metric_result.data else {}
    
    market_overview = market_result.data.get("overview") if market_result and market_result.data else {}
    market_cap = market_overview.get("market_cap")

    financials = result.data.get("financial_statements", {})
    revenue_ttm = _get_ttm(financials, "income", "total_revenue")
    if revenue_ttm is None and market_cap is not None:
        ps_ttm = fh_metrics.get("psTTM")
        if ps_ttm and ps_ttm > 0:
            revenue_ttm = market_cap / ps_ttm

    net_income_ttm = _get_ttm(financials, "income", "net_income")
    instants_shares = _instant_value(result.data.get("instants", {}), "shares")
    diluted_shares_ttm = _get_ttm(financials, "income", "weighted_average_shares_diluted") or instants_shares
    
    if diluted_shares_ttm is None and market_cap is not None:
        price = market_overview.get("price") or fh_metrics.get("regularMarketPrice") or 1
        if price > 0:
            diluted_shares_ttm = market_cap / price
            
    net_income_to_common_ttm = _get_ttm(financials, "income", "net_income_common_stockholders") or net_income_ttm
    
    if net_income_to_common_ttm is None and market_cap is not None:
        pe_ttm = fh_metrics.get("peTTM")
        if pe_ttm and pe_ttm > 0:
            net_income_to_common_ttm = market_cap / pe_ttm
        if net_income_ttm is None:
            net_income_ttm = net_income_to_common_ttm

    diluted_eps_ttm = _get_ttm(financials, "income", "earnings_per_share_diluted") or _safe_ratio(net_income_ttm, diluted_shares_ttm)
    total_assets_mrq = _get_mrq(financials, "balance_sheet", "total_assets")
    total_liabilities_mrq = _get_mrq(financials, "balance_sheet", "total_liabilities")
    total_equity_mrq = _get_mrq(financials, "balance_sheet", "stockholders_equity")
    if total_equity_mrq is None and total_assets_mrq is not None and total_liabilities_mrq is not None:
        total_equity_mrq = total_assets_mrq - total_liabilities_mrq
    if total_equity_mrq is None and market_cap is not None:
        pb_quarterly = fh_metrics.get("pbQuarterly")
        if pb_quarterly and pb_quarterly > 0:
            total_equity_mrq = market_cap / pb_quarterly
            
    cash_eq = _get_mrq(financials, "balance_sheet", "cash")
    short_term_investments = _get_mrq(financials, "balance_sheet", "marketable_securities_current") or 0
    total_cash_mrq = (cash_eq or 0) + short_term_investments if cash_eq is not None else None
    
    if total_cash_mrq is None and total_equity_mrq is not None:
        total_cash_mrq = None

    debt_current = result.data.get("instants", {}).get("debt_current")
    debt_noncurrent = result.data.get("instants", {}).get("debt_noncurrent")
    total_debt_mrq = _get_mrq(financials, "balance_sheet", "total_debt") or _sum_required_values(debt_current, debt_noncurrent)
    
    if total_debt_mrq is None and total_equity_mrq is not None:
        debt_to_equity = fh_metrics.get("totalDebt/totalEquityQuarterly")
        if debt_to_equity is not None:
            total_debt_mrq = total_equity_mrq * debt_to_equity
    operating_cash_flow_ttm = _get_ttm(financials, "cash_flow", "operating_cash_flow")
    capital_expenditure_ttm = _get_ttm(financials, "cash_flow", "capital_expenditure")
    free_cash_flow_ttm = operating_cash_flow_ttm - capital_expenditure_ttm if operating_cash_flow_ttm is not None and capital_expenditure_ttm is not None else None
    
    if free_cash_flow_ttm is None and market_cap is not None:
        pfcf_share_ttm = fh_metrics.get("pfcfShareTTM")
        if pfcf_share_ttm and pfcf_share_ttm > 0:
            free_cash_flow_ttm = market_cap / pfcf_share_ttm

    currency = latest_revenue.get("unit") if latest_revenue else None

    profit_margin = _safe_ratio(net_income_ttm, revenue_ttm)
    return_on_assets = _safe_ratio(net_income_ttm, total_assets_mrq)
    return_on_equity = _safe_ratio(net_income_ttm, total_equity_mrq)
    debt_to_equity = _safe_ratio(total_debt_mrq, total_equity_mrq)

    modules = {
        "company_overview": _module(
            {
                "company_name": result.data["company_name"],
                "cik": result.data["cik"],
                "description": None,
                "sector": f"SIC {profile['sic']}" if profile.get("sic") else None,
                "industry": profile.get("sic_description"),
                "exchange": profile.get("exchange"),
                "fiscal_year_end": profile.get("fiscal_year_end"),
                "state_of_incorporation": profile.get("state_of_incorporation"),
                "entity_type": profile.get("entity_type"),
                "filer_category": profile.get("filer_category"),
                "phone": profile.get("phone"),
                "business_address": profile.get("business_address"),
                "former_names": profile.get("former_names", []),
            },
            "Company identity and SIC classification are sourced from SEC EDGAR.",
            base_source_refs,
            status="partial",
        ),
        "eps_trend": _module(
            {"points": result.data["quarterly_eps"]},
            "Reported quarterly EPS from SEC filings. Provider estimates are not included.",
            base_source_refs,
            status="success" if result.data["quarterly_eps"] else "partial",
        ),
        "revenue_earnings": _module(
            {
                "period_type": "annual",
                "points": financial_trend,
                "currency": latest_revenue["unit"] if latest_revenue else None,
            },
            "Annual revenue and net income reported in SEC filings.",
            base_source_refs,
            status="success" if financial_trend else "partial",
        ),
        "financial_highlights": _module(
            {
                "metrics": {
                    "revenue_ttm": {
                        "value": revenue_ttm,
                        "status": "derived" if revenue_ttm is not None else "unavailable",
                        "basis": "ttm_total_revenue",
                        "input_refs": [],
                    },
                    "profit_margin": {
                        "value": profit_margin,
                        "status": (
                            "derived"
                            if profit_margin is not None
                            else "unavailable"
                        ),
                        "basis": "ttm_net_income / ttm_total_revenue",
                        "input_refs": ["net_income", "total_revenue"],
                    },
                    "return_on_assets": {
                        "value": return_on_assets,
                        "status": (
                            "derived"
                            if return_on_assets is not None
                            else "unavailable"
                        ),
                        "basis": "ttm_net_income / mrq_total_assets",
                        "input_refs": ["net_income", "total_assets"],
                    },
                    "return_on_equity": {
                        "value": return_on_equity,
                        "status": (
                            "derived"
                            if return_on_equity is not None
                            else "unavailable"
                        ),
                        "basis": "ttm_net_income / mrq_total_equity",
                        "input_refs": ["net_income", "stockholders_equity"],
                    },
                    "net_income_to_common": {
                        "value": net_income_to_common_ttm,
                        "status": "derived" if net_income_to_common_ttm is not None else "unavailable",
                        "basis": "ttm_net_income_common_stockholders",
                        "input_refs": [],
                    },
                    "diluted_eps": {
                        "value": diluted_eps_ttm,
                        "status": "derived" if diluted_eps_ttm is not None else "unavailable",
                        "basis": "ttm_eps_diluted or (ttm_net_income / ttm_diluted_shares)",
                        "input_refs": [],
                    },
                    "total_cash": {
                        "value": total_cash_mrq,
                        "status": "derived" if total_cash_mrq is not None else "unavailable",
                        "basis": "mrq_cash + mrq_short_term_investments",
                        "input_refs": [],
                    },
                    "total_debt_to_equity": {
                        "value": debt_to_equity,
                        "status": (
                            "derived"
                            if debt_to_equity is not None
                            else "unavailable"
                        ),
                        "basis": "mrq_total_debt / mrq_total_equity",
                        "input_refs": ["total_debt", "stockholders_equity"],
                    },
                    "levered_free_cash_flow": {
                        "value": free_cash_flow_ttm,
                        "status": "derived" if free_cash_flow_ttm is not None else "unavailable",
                        "basis": "ttm_operating_cash_flow - ttm_capital_expenditure",
                        "input_refs": [],
                    },
                },
                "base_metrics": {
                    "revenue_ttm": revenue_ttm,
                    "net_income_ttm": net_income_ttm,
                    "total_assets_mrq": total_assets_mrq,
                    "total_equity_mrq": total_equity_mrq,
                    "diluted_shares_ttm": diluted_shares_ttm,
                    "total_cash_mrq": total_cash_mrq,
                    "total_debt_mrq": total_debt_mrq,
                    "free_cash_flow_ttm": free_cash_flow_ttm,
                    "currency": currency,
                }
            },
            "Reported SEC facts and explicitly labeled app-derived ratios.",
            base_source_refs,
            status="partial",
        ),
    }
    revenue_mix = result.data.get("revenue_mix") or {}
    revenue_mix_source_index = result.data.get("revenue_mix_source_index")
    if revenue_mix and isinstance(revenue_mix_source_index, int):
        revenue_source_refs = (
            [source_refs[revenue_mix_source_index]]
            if revenue_mix_source_index < len(source_refs)
            else base_source_refs
        )
        modules["revenue_mix"] = _module(
            revenue_mix,
            (
                "Reported revenue mix extracted from SEC XBRL dimensions and "
                "reconciled to total fiscal revenue."
            ),
            revenue_source_refs,
        )
    supply_chain = result.data.get("supply_chain") or {}
    exposure = supply_chain.get("supply_chain_exposure") or {}
    supply_chain_indexes = result.data.get("supply_chain_source_indexes") or []
    supply_chain_refs = [
        source_refs[index]
        for index in supply_chain_indexes
        if isinstance(index, int) and index < len(source_refs)
    ]
    has_exposure = any(
        exposure.get(key)
        for key in (
            "suppliers",
            "manufacturing_locations",
            "raw_material_dependencies",
            "customer_concentrations",
            "risks",
        )
    )
    if supply_chain.get("analyzed_filings"):
        extraction = supply_chain.get("extraction") or {}
        supply_chain_message = (
            "AI-assisted SEC extraction with exact-evidence validation "
            "from the latest annual and quarterly filings."
            if extraction.get("method") == "ai"
            else "Deterministic SEC extraction from the latest available "
            "annual and quarterly filings."
        )
        if extraction.get("cache_source"):
            supply_chain_message += (
                f" Extraction cache: {extraction['cache_source']}."
            )
        if extraction.get("fallback_used"):
            supply_chain_message += (
                " AI was unavailable; deterministic filing extraction was "
                f"used ({extraction.get('fallback_reason') or 'unknown reason'})."
            )
        modules["supply_chain"] = _module(
            supply_chain,
            supply_chain_message,
            supply_chain_refs,
            status="success" if has_exposure else "partial",
        )
    customer_mix = result.data.get("customer_mix") or {}
    mix = customer_mix.get("customer_mix") or {}
    customer_mix_indexes = (
        result.data.get("customer_mix_source_indexes") or []
    )
    customer_mix_refs = [
        source_refs[index]
        for index in customer_mix_indexes
        if isinstance(index, int) and index < len(source_refs)
    ]
    has_customer_mix = any(
        mix.get(key)
        for key in (
            "major_customers",
            "customer_types",
            "channel_dependencies",
            "end_markets",
            "risks",
        )
    )
    if customer_mix.get("analyzed_filings"):
        customer_mix_extraction = customer_mix.get("extraction") or {}
        if customer_mix_extraction.get("method") == "ai":
            customer_mix_message = (
                "AI-assisted SEC customer-mix extraction with deterministic "
                "evidence validation."
            )
        elif customer_mix_extraction.get("fallback_used"):
            customer_mix_message = (
                "Deterministic SEC customer-mix extraction used after all "
                "configured AI models were unavailable."
            )
        else:
            customer_mix_message = (
                "Deterministic customer-mix extraction from explicit "
                "disclosures in the latest annual and quarterly SEC filings."
            )
        if customer_mix_extraction.get("cache_source"):
            customer_mix_message += (
                " Extraction cache: "
                f"{customer_mix_extraction['cache_source']}."
            )
        modules["customer_mix"] = _module(
            customer_mix,
            customer_mix_message,
            customer_mix_refs,
            status="success" if has_customer_mix else "partial",
        )
    return modules


def _build_market_modules(
    result: ProviderResult,
    source_refs: list[int],
) -> dict[str, SummaryModule]:
    if result.data is None:
        return {}
    quote = result.data["quote"]
    overview = result.data["overview"]
    points = result.data["price_history"]
    provider_name = result.sources[0].provider if result.sources else "market provider"
    modules: dict[str, SummaryModule] = {}

    if quote:
        modules["quote"] = _module(
            {**quote, **{
                "company_name": overview.get("name") if overview else None,
                "exchange": overview.get("exchange") if overview else None,
                "currency": overview.get("currency") if overview else None,
                "market_state": quote.get("marketState", "REGULAR"),
                "regularMarketPrice": quote.get("regularMarketPrice"),
                "regularMarketChangePercent": quote.get("regularMarketChangePercent"),
                "extendedPrice": quote.get("extendedPrice"),
                "extendedChange": quote.get("extendedChange"),
                "extendedChangePercent": quote.get("extendedChangePercent"),
                "extendedHoursTimestamp": quote.get("extendedHoursTimestamp"),
            }},
            f"Latest sourced close from {provider_name}.",
            source_refs,
        )
    if points:
        modules["price_history"] = _module(
            {
                "interval": result.data.get("interval", "unknown"),
                "points": points,
            },
            f"Historical market prices from {provider_name}.",
            source_refs,
        )
        modules["performance"] = _module(
            {"returns": _performance(points), "benchmark": None},
            "Price returns are calculated from sourced closes; benchmark data is not configured.",
            source_refs,
            status="partial",
        )
    if quote or overview:
        modules["key_facts"] = _module(
            {
                "previous_close": quote.get("previous_close") if quote else None,
                "day_range": {
                    "low": quote.get("period_low") if quote else None,
                    "high": quote.get("period_high") if quote else None,
                },
                "range_label": quote.get("range_label", "Latest week range")
                if quote
                else "Market range",
                "week_52_range": {
                    "low": overview.get("week_52_low") if overview else None,
                    "high": overview.get("week_52_high") if overview else None,
                },
                "market_cap": overview.get("market_cap") if overview else None,
                "pe_ratio": overview.get("pe_ratio") if overview else None,
                "eps": overview.get("eps") if overview else None,
                "dividend_yield": {
                    "value": None,
                    "status": "unavailable",
                    "basis": "Dividend history is unavailable.",
                    "input_refs": [],
                    "period_type": None,
                    "dividend_per_share": None,
                    "period_end": None,
                },
                "next_earnings": None,
            },
            f"Market facts from {provider_name}.",
            source_refs,
            status="partial",
        )
    if overview and any(
        overview.get(field) for field in ("description", "sector", "industry")
    ):
        modules["company_overview"] = _module(
            {
                "company_name": overview.get("name"),
                "description": overview.get("description"),
                "sector": overview.get("sector"),
                "industry": overview.get("industry"),
            },
            f"Company profile from {provider_name}.",
            source_refs,
        )
    if overview and any(
        overview.get(field)
        for field in (
            "market_cap",
            "pe_ratio",
            "forward_pe",
            "price_to_sales",
            "ev_to_ebitda",
        )
    ):
        modules["valuation_measures"] = _module(
            {
                "metrics": {
                    "enterprise_value": None,
                    "trailing_pe": overview.get("pe_ratio"),
                    "forward_pe": overview.get("forward_pe"),
                    "peg_ratio": overview.get("peg_ratio"),
                    "price_to_sales": overview.get("price_to_sales"),
                    "ev_to_ebitda": overview.get("ev_to_ebitda"),
                }
            },
            "Provider valuation measures; unavailable values remain null.",
            source_refs,
            status="partial",
        )
    return modules


def _derived_metric(
    value: float | None,
    basis: str,
    input_refs: list[str],
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "status": status or ("derived" if value is not None else "unavailable"),
        "basis": basis,
        "input_refs": input_refs,
    }


def _dividend_yield_metric(
    sec_result: ProviderResult,
    market_result: ProviderResult,
) -> dict[str, Any]:
    market_data = market_result.data or {}
    quote = market_data.get("quote") or {}
    price = quote.get("price")
    latest_day = quote.get("latest_trading_day")
    dividends = market_data.get("dividends") or []

    if price not in {None, 0} and latest_day and dividends:
        trailing_end = date.fromisoformat(latest_day)
        trailing_start = trailing_end - timedelta(days=365)
        trailing = [
            item
            for item in dividends
            if (
                item.get("type") == "Cash"
                and item.get("currency") == "USD"
                and item.get("amount") is not None
                and trailing_start
                < date.fromisoformat(item["ex_date"])
                <= trailing_end
            )
        ]
        if trailing:
            dividend_per_share = sum(item["amount"] for item in trailing)
            return {
                **_derived_metric(
                    dividend_per_share / price,
                    (
                        f"cash dividends with ex-dates from "
                        f"{trailing_start.isoformat()} through "
                        f"{trailing_end.isoformat()} / latest market price"
                    ),
                    ["nasdaq_dividend_events", "market_price"],
                ),
                "period_type": "ttm",
                "dividend_per_share": dividend_per_share,
                "period_end": trailing_end.isoformat(),
            }

    annual_dividends = (
        (sec_result.data or {})
        .get("annual", {})
        .get("dividends_per_share", [])
    )
    latest_annual = _latest(annual_dividends)
    if (
        price not in {None, 0}
        and (sec_result.data or {}).get("security_basis_compatible")
        and latest_annual
        and latest_annual.get("unit") == "USD/shares"
    ):
        return {
            **_derived_metric(
                latest_annual["value"] / price,
                (
                    f"fiscal {_period_label(latest_annual)} dividends declared "
                    "per share / latest market price"
                ),
                ["sec_fiscal_dividends_per_share", "market_price"],
            ),
            "period_type": "fiscal",
            "dividend_per_share": latest_annual["value"],
            "period_end": latest_annual.get("end"),
        }

    return {
        **_derived_metric(
            None,
            (
                "No security-compatible trailing or fiscal dividend-per-share "
                "amount is available."
            ),
            [],
        ),
        "period_type": None,
        "dividend_per_share": None,
        "period_end": None,
    }


def _build_derived_valuation_modules(
    sec_result: ProviderResult,
    market_result: ProviderResult,
    source_refs: list[int],
    fh_metric_result: ProviderResult | None = None,
) -> dict[str, SummaryModule]:
    if sec_result.data is None or market_result.data is None:
        return {}

    annual = sec_result.data["annual"]
    instants = sec_result.data["instants"]
    cash = instants.get("cash")
    debt_current = instants.get("debt_current")
    debt_noncurrent = instants.get("debt_noncurrent")
    latest_revenue = _latest(annual["revenue"])
    latest_income = _latest(annual["net_income"])
    latest_eps = _latest(annual["eps"])
    latest_operating_income = _latest(annual["operating_income"])
    latest_depreciation = _latest(annual["depreciation_amortization"])

    fh_metrics = fh_metric_result.data if fh_metric_result and fh_metric_result.data else {}

    market_overview = market_result.data.get("overview") or {}
    market_cap = market_overview.get("market_cap")

    financials = sec_result.data.get("financial_statements", {})
    revenue_ttm = _get_ttm(financials, "income", "total_revenue")
    if revenue_ttm is None and market_cap is not None:
        ps_ttm = fh_metrics.get("psTTM")
        if ps_ttm and ps_ttm > 0:
            revenue_ttm = market_cap / ps_ttm

    net_income_ttm = _get_ttm(financials, "income", "net_income")
    if net_income_ttm is None and market_cap is not None:
        pe_ttm = fh_metrics.get("peTTM")
        if pe_ttm and pe_ttm > 0:
            net_income_ttm = market_cap / pe_ttm

    ebit_ttm = _get_ttm(financials, "income", "operating_income")
    da_ttm = _get_ttm(financials, "cash_flow", "depreciation_amortization")
    ebitda_ttm = ebit_ttm + da_ttm if ebit_ttm is not None and da_ttm is not None else None
    
    shares_outstanding_mrq = _get_mrq(financials, "balance_sheet", "shares_outstanding")
    if shares_outstanding_mrq is None and market_cap is not None:
        price = market_overview.get("price") or fh_metrics.get("regularMarketPrice") or 1
        if price > 0:
            shares_outstanding_mrq = market_cap / price

    debt_current = sec_result.data.get("instants", {}).get("debt_current")
    debt_noncurrent = sec_result.data.get("instants", {}).get("debt_noncurrent")
    total_debt_mrq = _get_mrq(financials, "balance_sheet", "total_debt") or _sum_required_values(debt_current, debt_noncurrent)
    if total_debt_mrq is None and market_cap is not None:
        debt_to_equity = fh_metrics.get("totalDebt/totalEquityQuarterly")
        if debt_to_equity is not None:
            # We will calculate total_debt_mrq after total_equity_mrq
            pass

    total_assets_mrq = _get_mrq(financials, "balance_sheet", "total_assets")
    total_liabilities_mrq = _get_mrq(financials, "balance_sheet", "total_liabilities")
    total_equity_mrq = _get_mrq(financials, "balance_sheet", "stockholders_equity")
    
    if total_equity_mrq is None and total_assets_mrq is not None and total_liabilities_mrq is not None:
        total_equity_mrq = total_assets_mrq - total_liabilities_mrq
    if total_equity_mrq is None and market_cap is not None:
        pb_quarterly = fh_metrics.get("pbQuarterly")
        if pb_quarterly and pb_quarterly > 0:
            total_equity_mrq = market_cap / pb_quarterly

    if total_debt_mrq is None and total_equity_mrq is not None:
        debt_to_equity = fh_metrics.get("totalDebt/totalEquityQuarterly")
        if debt_to_equity is not None:
            total_debt_mrq = total_equity_mrq * debt_to_equity
            
    cash_eq = _get_mrq(financials, "balance_sheet", "cash")
    short_term_investments = _get_mrq(financials, "balance_sheet", "marketable_securities_current") or 0
    total_cash_mrq = (cash_eq or 0) + short_term_investments if cash_eq is not None else None
    
    if total_cash_mrq is None and total_equity_mrq is not None:
        # estimate cash from total_assets if possible, else fallback to 0
        total_cash_mrq = None
        
    enterprise_value = None
    if market_cap is not None:
        safe_debt = total_debt_mrq if total_debt_mrq is not None else 0
        safe_cash = total_cash_mrq if total_cash_mrq is not None else 0
        enterprise_value = market_cap + safe_debt - safe_cash

    if ebitda_ttm is None and enterprise_value is not None:
        ev_ebitda_ttm = fh_metrics.get("evEbitdaTTM")
        if ev_ebitda_ttm and ev_ebitda_ttm > 0:
            ebitda_ttm = enterprise_value / ev_ebitda_ttm

    book_value_per_share_mrq = _safe_ratio(total_equity_mrq, shares_outstanding_mrq)

    market_cap_basis = market_overview.get("market_cap_basis")
    total_debt = _sum_required_values(debt_current, debt_noncurrent)
    balance_sheet_inputs_match = (
        cash is not None
        and debt_current is not None
        and debt_noncurrent is not None
        and cash.get("unit") == "USD"
        and cash.get("unit") == debt_current.get("unit") == debt_noncurrent.get("unit")
        and cash.get("period")
        == debt_current.get("period")
        == debt_noncurrent.get("period")
    )

    market_cap_metric = _derived_metric(
        market_cap,
        market_cap_basis
        or "Market capitalization is unavailable from the market-data provider.",
        ["nasdaq_market_cap"] if market_cap is not None else [],
        status="provider" if market_cap is not None else "unavailable",
    )

    dividend_yield = _dividend_yield_metric(sec_result, market_result)

    market_modules = _build_market_modules(
        market_result,
        source_refs,
    )
    # SEC remains the source of company identity/profile when it is available.
    # Nasdaq overview fields are market metadata and must not replace the SEC
    # company module with a ticker symbol or a less specific profile.
    market_modules.pop("company_overview", None)
    quote_module = market_modules.get("quote")
    if quote_module and quote_module.data is not None:
        profile = sec_result.data.get("profile", {})
        quote_module.data["company_name"] = sec_result.data.get("company_name")
        quote_module.data["exchange"] = profile.get("exchange")
        quote_module.data["currency"] = "USD"
        quote_module.source_refs = source_refs

    trailing_pe = _derived_metric(
        _safe_ratio(market_cap, net_income_ttm),
        "market_cap / ttm_net_income",
        ["market_cap", "net_income"],
    )
    price_to_sales = _derived_metric(
        _safe_ratio(market_cap, revenue_ttm),
        "market_cap / ttm_revenue",
        ["market_cap", "revenue"],
    )
    price_to_book = _derived_metric(
        _safe_ratio(market_cap, total_equity_mrq),
        "market_cap / mrq_total_equity",
        ["market_cap", "stockholders_equity"],
    )
    ev_to_revenue = _derived_metric(
        _safe_ratio(enterprise_value, revenue_ttm),
        "enterprise_value / ttm_revenue",
        ["market_cap", "total_debt", "cash", "revenue"],
    )
    enterprise_value_metric = _derived_metric(
        enterprise_value,
        "market_cap + mrq_total_debt - mrq_total_cash",
        ["market_cap", "total_debt", "cash"],
    )
    ev_to_ebitda = _derived_metric(
        _safe_ratio(enterprise_value, ebitda_ttm),
        "enterprise_value / ttm_ebitda",
        [
            "market_cap",
            "total_debt",
            "cash",
            "operating_income",
            "depreciation_amortization",
        ],
    )
    
    nasdaq_overview = market_result.data.get("overview") or {}
    forward_pe = nasdaq_overview.get("forward_pe")
    peg_ratio = nasdaq_overview.get("peg_ratio")

    key_facts = market_modules.get("key_facts")
    if key_facts and key_facts.data is not None:
        key_facts.data["market_cap"] = market_cap_metric
        key_facts.data["pe_ratio"] = trailing_pe
        key_facts.data["dividend_yield"] = dividend_yield
        key_facts.data["eps"] = (
            latest_eps
            if (
                sec_result.data.get("security_basis_compatible")
                and latest_eps
                and latest_eps.get("unit") == "USD/shares"
            )
            else None
        )
        key_facts.source_refs = source_refs

    market_modules["valuation_measures"] = _module(
        {
            "metrics": {
                "market_cap": market_cap_metric,
                "enterprise_value": enterprise_value_metric,
                "trailing_pe": trailing_pe,
                "forward_pe": _derived_metric(forward_pe, "nasdaq_forward_pe", [], status="provider" if forward_pe else "unavailable"),
                "peg_ratio": _derived_metric(peg_ratio, "nasdaq_peg_ratio", [], status="provider" if peg_ratio else "unavailable"),
                "price_to_sales": price_to_sales,
                "price_to_book": price_to_book,
                "ev_to_revenue": ev_to_revenue,
                "ev_to_ebitda": ev_to_ebitda,
            },
            "base_metrics": {
                "shares_outstanding_mrq": shares_outstanding_mrq,
                "total_debt_mrq": total_debt_mrq,
                "total_cash_mrq": total_cash_mrq,
                "net_income_ttm": net_income_ttm,
                "revenue_ttm": revenue_ttm,
                "book_value_per_share_mrq": book_value_per_share_mrq,
                "ebitda_ttm": ebitda_ttm,
                "forward_pe": forward_pe,
                "peg_ratio": peg_ratio,
            }
        },
        "App-derived valuation measures using Nasdaq price and SEC filing facts.",
        source_refs,
        status="partial",
    )
    return market_modules


def build_summary_response(ticker: str) -> SummaryResponse:
    settings = get_settings()
    modules: dict[str, SummaryModule] = {}
    sources: list[SourceRecord] = []
    warnings: list[str] = []

    if settings.enable_live_providers:
        # get_unified_financials_sync encapsulates SecCompanyFactsProvider
        # and adds the Alpha Vantage quarterly fallback for foreign issuers
        market_provider = NasdaqMarketProvider(
            timeout_seconds=settings.provider_timeout_seconds,
        )

        finnhub_provider = FinnhubMetricProvider(api_key=settings.finnhub_api_key)

        with ThreadPoolExecutor(max_workers=3) as executor:
            sec_future = executor.submit(
                get_unified_financials_sync,
                ticker,
                settings.supply_chain_ai_enabled,
                settings.customer_mix_ai_enabled,
                settings.gemini_api_key,
                settings.gemini_supply_chain_model,
                settings.gemini_customer_mix_primary_model,
                settings.gemini_customer_mix_secondary_model
            )
            market_future = (
                executor.submit(market_provider.fetch, ticker)
                if market_provider is not None
                else None
            )
            fh_metric_future = executor.submit(finnhub_provider.fetch, ticker)
            sec_result = sec_future.result()
            market_result = market_future.result() if market_future else None
            fh_metric_result = fh_metric_future.result()

            if market_result is not None and market_result.data is not None:
                overview = market_result.data.setdefault("overview", {})
                if overview.get("forward_pe") is None:
                    overview["forward_pe"] = fh_metric_result.data.get("forwardPE")
                if overview.get("peg_ratio") is None:
                    peg = fh_metric_result.data.get("pegRatio")
                    if peg is None:
                        pe = overview.get("pe_ratio") or overview.get("forward_pe")
                        div_growth = fh_metric_result.data.get("dividendGrowthRate5Y")
                        if pe is not None and div_growth:
                            peg = pe / div_growth
                    overview["peg_ratio"] = peg

        sec_refs: list[int] = []
        warnings.extend(sec_result.warnings)
        if (
            sec_result.data is not None
            and not sec_result.data.get("security_basis_compatible", False)
        ):
            warnings.append(
                "Per-share SEC facts are not shown because the issuer's "
                "reported common-share basis is not verified against the "
                "US-traded security."
            )
        if sec_result.sources:
            sec_refs = list(
                range(len(sources), len(sources) + len(sec_result.sources))
            )
            sources.extend(_source_records(sec_result))
            modules.update(_build_sec_modules(sec_result, sec_refs, fh_metric_result, market_result))

        if market_result is not None:
            warnings.extend(market_result.warnings)
            if market_result.sources:
                market_refs = list(
                    range(
                        len(sources),
                        len(sources) + len(market_result.sources),
                    )
                )
                sources.extend(_source_records(market_result))
                if sec_result.data is not None:
                    modules.update(
                        _build_derived_valuation_modules(
                            sec_result,
                            market_result,
                            [*sec_refs, *market_refs],
                            fh_metric_result,
                        )
                    )
                else:
                    modules.update(
                        _build_market_modules(market_result, market_refs)
                    )
        else:
            warnings.append("No market-data provider is configured.")
    else:
        warnings.append("Live providers are disabled by ENABLE_LIVE_PROVIDERS.")

    data = SummaryData(
        quote=modules.get("quote", unavailable_module("quote")),
        price_history=modules.get(
            "price_history", unavailable_module("price_history")
        ),
        key_facts=modules.get("key_facts", unavailable_module("key_facts")),
        company_overview=modules.get(
            "company_overview", unavailable_module("company_overview")
        ),
        revenue_mix=modules.get(
            "revenue_mix",
            unavailable_revenue_mix(ticker),
        ),
        supply_chain=modules.get(
            "supply_chain",
            unavailable_supply_chain(ticker),
        ),
        customer_mix=modules.get(
            "customer_mix",
            unavailable_customer_mix(ticker),
        ),
        performance=modules.get("performance", unavailable_module("performance")),
        eps_trend=modules.get("eps_trend", unavailable_module("eps_trend")),
        revenue_earnings=modules.get(
            "revenue_earnings", unavailable_module("revenue_earnings")
        ),
        valuation_measures=modules.get(
            "valuation_measures", unavailable_module("valuation_measures")
        ),
        financial_highlights=modules.get(
            "financial_highlights", unavailable_module("financial_highlights")
        ),
        peer_comparison=unavailable_module("peer_comparison"),
    )

    data_modules = [
        data.quote,
        data.price_history,
        data.key_facts,
        data.company_overview,
        data.revenue_mix,
        data.supply_chain,
        data.customer_mix,
        data.performance,
        data.eps_trend,
        data.revenue_earnings,
        data.valuation_measures,
        data.financial_highlights,
        data.peer_comparison,
    ]
    available_count = sum(
        module.status != "unavailable" for module in data_modules
    )
    response_status = (
        "unavailable"
        if available_count == 0
        else "success"
        if available_count == len(data_modules)
        else "partial"
    )
    source_dates = [
        source.source_timestamp for source in sources if source.source_timestamp
    ]

    return SummaryResponse(
        ticker=ticker,
        status=response_status,
        as_of=max(source_dates, default=None),
        data=data,
        sources=sources,
        warnings=warnings,
    )
