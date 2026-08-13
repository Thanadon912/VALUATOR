import asyncio
import copy
from typing import Any
import time

from app.providers.base import ProviderResult
from app.models import SourceRecord
from app.providers.sec import SecCompanyFactsProvider
from app.providers.fmp_financials import FMPFinancialsProvider
from app.core.config import get_settings
from app.providers.sec_financials import STATEMENT_ROWS
from app.repositories import close_cache_repository

def _safe_float(val: Any) -> float | None:
    if val is None or val == "None" or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None

def _first_number(report: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(report.get(key))
        if value is not None:
            return value
    return None


def _map_fmp_to_sec_rows(fmp_data: list[dict], statement: str, existing_rows: list[dict], is_annual: bool = False) -> tuple[list[dict], list[dict]]:
    if not fmp_data:
        return existing_rows, []

    # Map periods
    periods = []
    # Reverse to have oldest first or newest first? The SEC data is usually sorted. AV returns newest first.
    # Let's keep AV order or sort by date. AV is newest first. We'll reverse to make it oldest to newest.
    fmp_data_sorted = sorted(fmp_data, key=lambda x: x.get("date", ""))
    
    # AV format uses fiscalDateEnding
    for report in fmp_data_sorted:
        date_end = report.get("date")
        if not date_end:
            continue
        # simple period key, e.g. Q1, Q2, etc. AV doesn't provide Q1/Q2 easily, we can use the date
        prefix = "FMP_A" if is_annual else "FMP_Q"
        period_key = f"{prefix}_{date_end}"
        periods.append({
            "key": period_key,
            "label": date_end,
            "period_end": date_end,
            "period_start": report.get("calendarYear"),
            "fiscal_period": report.get("period") or ("FY" if is_annual else "Q"),
            "statement_period": "annual" if is_annual else "quarterly",
            "source_ref": 0
        })

    # Deep copy rows to avoid mutating original empty template
    if not existing_rows:
        new_rows = []
        for definition in STATEMENT_ROWS.get(statement, []):
            new_rows.append({
                "id": definition.id,
                "label": definition.label,
                "depth": definition.depth,
                "kind": definition.kind,
                "parent_id": definition.parent_id,
                "cells": {},
            })
    else:
        new_rows = copy.deepcopy(existing_rows)

    if statement == "income" and not any(row["id"] == "shares_outstanding" for row in new_rows):
        new_rows.append({
            "id": "shares_outstanding",
            "label": "Shares Outstanding",
            "depth": 0,
            "kind": "line",
            "parent_id": None,
            "cells": {},
        })

    # Mapping logic per statement type
    for row in new_rows:
        row_id = row["id"]
        cells = row.get("cells", {})
        for report in fmp_data_sorted:
            date_end = report.get("date")
            if not date_end:
                continue
            prefix = "FMP_A" if is_annual else "FMP_Q"
            period_key = f"{prefix}_{date_end}"
            
            val = None
            if statement == "income":
                if row_id == "total_revenue":
                    val = _safe_float(report.get("revenue"))
                elif row_id == "cost_of_revenue":
                    val = _safe_float(report.get("costOfRevenue"))
                elif row_id == "gross_profit":
                    val = _safe_float(report.get("grossProfit"))
                elif row_id == "operating_expense":
                    val = _safe_float(report.get("operatingExpenses"))
                elif row_id == "research_development":
                    val = _safe_float(report.get("researchAndDevelopmentExpenses"))
                elif row_id == "selling_general_admin":
                    val = _safe_float(report.get("sellingGeneralAndAdministrative"))
                elif row_id == "operating_income":
                    val = _safe_float(report.get("operatingIncome"))
                elif row_id == "interest_expense":
                    val = _first_number(report, "interestExpense", "interestExpenseNonOperating")
                elif row_id == "other_income_expense":
                    val = _safe_float(report.get("totalOtherIncomeExpensesNet"))
                elif row_id == "pretax_income":
                    val = _safe_float(report.get("incomeBeforeTax"))
                elif row_id == "tax_provision":
                    val = _safe_float(report.get("incomeTaxExpense"))
                elif row_id == "net_income":
                    val = _safe_float(report.get("netIncome"))
                elif row_id == "depreciation_amortization":
                    val = _safe_float(report.get("depreciationAndAmortization"))
                elif row_id in {"diluted_average_shares", "shares_outstanding"}:
                    val = _first_number(report, "weightedAverageShsOutDil", "weightedAverageShsOut")
                elif row_id == "basic_average_shares":
                    val = _first_number(report, "weightedAverageShsOut", "weightedAverageShsOutDil")
            elif statement == "balance_sheet":
                if row_id == "cash":
                    val = _safe_float(report.get("cashAndCashEquivalents"))
                elif row_id == "receivables":
                    val = _safe_float(report.get("netReceivables"))
                elif row_id == "inventory":
                    val = _safe_float(report.get("inventory"))
                elif row_id == "current_assets":
                    val = _safe_float(report.get("totalCurrentAssets"))
                elif row_id == "property_plant_equipment":
                    val = _safe_float(report.get("propertyPlantEquipmentNet"))
                elif row_id == "goodwill":
                    val = _safe_float(report.get("goodwill"))
                elif row_id == "intangible_assets":
                    val = _safe_float(report.get("intangibleAssets"))
                elif row_id == "total_assets":
                    val = _safe_float(report.get("totalAssets"))
                elif row_id == "accounts_payable":
                    val = _safe_float(report.get("accountPayables"))
                elif row_id == "current_liabilities":
                    val = _safe_float(report.get("totalCurrentLiabilities"))
                elif row_id == "short_term_debt":
                    val = _first_number(report, "shortTermDebt", "shortTermDebtTotal")
                elif row_id == "long_term_debt":
                    val = _safe_float(report.get("longTermDebt"))
                elif row_id == "total_debt":
                    val = _safe_float(report.get("totalDebt"))
                elif row_id == "total_liabilities":
                    val = _safe_float(report.get("totalLiabilities"))
                elif row_id == "retained_earnings":
                    val = _safe_float(report.get("retainedEarnings"))
                elif row_id == "stockholders_equity":
                    val = _safe_float(report.get("totalStockholdersEquity"))
                elif row_id == "shares_outstanding":
                    val = _safe_float(report.get("commonStockSharesOutstanding"))
            elif statement == "cash_flow":
                if row_id == "operating_cash_flow":
                    val = _safe_float(report.get("netCashProvidedByOperatingActivities"))
                elif row_id == "depreciation_amortization":
                    val = _safe_float(report.get("depreciationDepletionAndAmortization"))
                elif row_id == "change_in_working_capital":
                    val = _safe_float(report.get("changeInWorkingCapital"))
                elif row_id == "capital_expenditure":
                    val = _first_number(report, "capitalExpenditure", "capitalExpenditures")
                elif row_id == "free_cash_flow":
                    val = _safe_float(report.get("freeCashFlow"))
                elif row_id == "dividends_paid":
                    dividends = _first_number(
                        report,
                        "dividendsPaid",
                        "commonDividendsPaid",
                        "netDividendsPaid",
                    )
                    val = abs(dividends) if dividends is not None else None
                elif row_id == "financing_cash_flow":
                    val = _first_number(
                        report,
                        "netCashProvidedByFinancingActivities",
                        "netCashUsedProvidedByFinancingActivities",
                    )
                elif row_id == "cash_change":
                    val = _safe_float(report.get("netChangeInCash"))

            if val is not None:
                unit = (
                    "shares"
                    if row_id in {"basic_average_shares", "diluted_average_shares", "shares_outstanding"}
                    else report.get("reportedCurrency", "USD")
                )
                cells[period_key] = {
                    "value": val,
                    "unit": unit,
                    "status": "reported",
                    "concept": row_id,
                    "taxonomy": "FMP",
                    "data_status": "reported"
                }
        row["cells"] = cells

    return new_rows, periods

async def get_unified_financials(
    ticker: str,
    supply_chain_ai_enabled: bool = False,
    customer_mix_ai_enabled: bool = False,
    gemini_api_key: str | None = None,
    gemini_supply_chain_model: str | None = "gemini-3.1-flash-lite",
    gemini_customer_mix_primary_model: str | None = "gemini-3.1-flash-lite",
    gemini_customer_mix_secondary_model: str | None = "gemini-2.5-flash-lite",
) -> ProviderResult:
    settings = get_settings()
    
    # 1. Fetch SEC data (this is sync in the existing codebase, we run it in a thread or just call it)
    sec_provider = SecCompanyFactsProvider(
        user_agent=settings.sec_user_agent,
        timeout_seconds=settings.provider_timeout_seconds,
        supply_chain_ai_enabled=supply_chain_ai_enabled,
        customer_mix_ai_enabled=customer_mix_ai_enabled,
        gemini_api_key=gemini_api_key,
        gemini_supply_chain_model=gemini_supply_chain_model,
        supply_chain_cache_dir=settings.supply_chain_cache_dir,
        gemini_customer_mix_primary_model=gemini_customer_mix_primary_model,
        gemini_customer_mix_secondary_model=gemini_customer_mix_secondary_model,
        customer_mix_cache_dir=settings.customer_mix_cache_dir,
    )
    # running synchronously is okay for this wrapper if we don't want to refactor SEC provider right now
    sec_result = sec_provider.fetch(ticker)
    
    if sec_result.data is None:
        return sec_result

    fs = sec_result.data.get("financial_statements", {})
    q = fs.get("quarterly", {})
    
    # FMP is authoritative for statement rows. SEC remains the source for
    # filing-derived profile and adaptive-valuation context.
    fmp_provider = FMPFinancialsProvider(
        api_key=settings.fmp_api_key,
        timeout_seconds=settings.provider_timeout_seconds,
    )
    vendor_result = await fmp_provider.fetch_financials(ticker)
    vendor_data = vendor_result.get("statements", {})
    sec_result.data["fmp_metadata"] = vendor_result.get("metadata", {})
    sec_result.data["analyst_estimates"] = vendor_result.get("analyst_estimates", [])
    sec_result.warnings.extend(vendor_result.get("warnings", []))

    # Map Vendor Data to SEC Schema
    for stmt_key, fmp_key in [
        ("income", "income_statement"),
        ("balance_sheet", "balance_sheet"),
        ("cash_flow", "cash_flow")
    ]:
        fmp_q_reports = vendor_data.get(fmp_key, {}).get("quarterly", [])
        if fmp_q_reports:
            existing_q_rows = q.get(stmt_key, {}).get("rows", [])
            new_q_rows, new_q_periods = _map_fmp_to_sec_rows(fmp_q_reports, stmt_key, existing_q_rows, is_annual=False)
            q[stmt_key]["rows"] = new_q_rows
            q[stmt_key]["periods"] = new_q_periods
            q[stmt_key]["unit_label"] = f"{fmp_q_reports[-1].get('reportedCurrency', 'USD')} (FMP)"

        fmp_a_reports = vendor_data.get(fmp_key, {}).get("annual", [])
        if fmp_a_reports:
            a = fs.get("annual", {})
            existing_a_rows = a.get(stmt_key, {}).get("rows", [])
            new_a_rows, new_a_periods = _map_fmp_to_sec_rows(fmp_a_reports, stmt_key, existing_a_rows, is_annual=True)
            if stmt_key not in a:
                a[stmt_key] = {}
            a[stmt_key]["rows"] = new_a_rows
            a[stmt_key]["periods"] = new_a_periods
            a[stmt_key]["unit_label"] = f"{fmp_a_reports[-1].get('reportedCurrency', 'USD')} (FMP)"
            fs["annual"] = a

    # Add source record
    sec_result.sources.append(
        SourceRecord(
            provider="Financial Modeling Prep (Vendor Override)",
            source_url="https://financialmodelingprep.com/",
            source_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            is_stale=False,
        )
    )

    # RE-CALCULATE ROLLING TTM FOR FOREIGN STOCKS
    # TTM Value = Q1 + Q2 + Q3 + Q4
    # The statistics calculation uses `_get_mrq` or `ttm` periods in the financials structure.
    # Actually, statistics.py computes TTM dynamically by looking at quarterly data or uses SEC 'ttm' period.
    # The SecCompanyFactsProvider generates a 'ttm' period in 'quarterly' statements if it has 4 quarters.
    # We should generate a TTM period for income and cash_flow statements based on the last 4 quarters!
    for stmt_key in ["income", "cash_flow"]:
        periods = q.get(stmt_key, {}).get("periods", [])
        if len(periods) >= 4:
            ttm_cells_by_row = {}
            for row in q[stmt_key].get("rows", []):
                # Duration rows sum. Share-count rows use latest quarter; adding
                # four weighted averages would overstate denominator by ~4x.
                total = 0
                count = 0
                units = set()
                selected_periods = (
                    periods[-1:]
                    if row["id"] in {"basic_average_shares", "diluted_average_shares", "shares_outstanding"}
                    else periods[-4:]
                )
                for p in selected_periods:
                    cell = row["cells"].get(p["key"])
                    if cell and cell.get("value") is not None:
                        total += cell["value"]
                        count += 1
                        if cell.get("unit"):
                            units.add(cell["unit"])
                expected_count = len(selected_periods)
                if count == expected_count and len(units) == 1:
                    # Valid TTM
                    ttm_cells_by_row[row["id"]] = {
                        "value": total,
                        "unit": next(iter(units)),
                        "status": "derived",
                        "concept": row["id"],
                        "taxonomy": "vendor",
                        "data_status": "derived",
                        "basis": (
                            "latest vendor quarter; share counts are non-additive"
                            if row["id"] in {"basic_average_shares", "diluted_average_shares", "shares_outstanding"}
                            else "sum of four comparable vendor quarters in the reported currency"
                        ),
                    }
            
            # Create a TTM period
            latest_period = periods[-1]
            ttm_key = f"TTM_{latest_period['key']}"
            periods.append({
                "key": ttm_key,
                "label": "TTM",
                "period_end": latest_period["period_end"],
                "period_start": periods[-4]["period_start"] or periods[-4]["period_end"], # Approx
                "fiscal_period": "TTM",
                "statement_period": "ttm",
                "source_ref": 0
            })
            for row in q[stmt_key].get("rows", []):
                if row["id"] in ttm_cells_by_row:
                    row["cells"][ttm_key] = ttm_cells_by_row[row["id"]]

    return sec_result

def get_unified_financials_sync(
    ticker: str,
    supply_chain_ai_enabled: bool = False,
    customer_mix_ai_enabled: bool = False,
    gemini_api_key: str | None = None,
    gemini_supply_chain_model: str | None = "gemini-3.1-flash-lite",
    gemini_customer_mix_primary_model: str | None = "gemini-3.1-flash-lite",
    gemini_customer_mix_secondary_model: str | None = "gemini-2.5-flash-lite",
) -> ProviderResult:
    async def run() -> ProviderResult:
        try:
            return await get_unified_financials(
                ticker,
                supply_chain_ai_enabled=supply_chain_ai_enabled,
                customer_mix_ai_enabled=customer_mix_ai_enabled,
                gemini_api_key=gemini_api_key,
                gemini_supply_chain_model=gemini_supply_chain_model,
                gemini_customer_mix_primary_model=gemini_customer_mix_primary_model,
                gemini_customer_mix_secondary_model=gemini_customer_mix_secondary_model,
            )
        finally:
            await close_cache_repository()

    return asyncio.run(run())
