from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal


StatementType = Literal["income", "balance_sheet", "cash_flow"]
StatementPeriod = Literal["annual", "quarterly"]
PeriodKind = Literal["duration", "instant", "derived"]

ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
QUARTERLY_FORMS = {"10-Q", "10-K", "6-K", "20-F", "40-F"}


@dataclass(frozen=True)
class RowDefinition:
    id: str
    label: str
    kind: str
    depth: int
    parent_id: str | None
    period_kind: PeriodKind
    concepts: tuple[str, ...] = ()
    preferred_units: tuple[str, ...] = ("USD",)


INCOME_ROWS: tuple[RowDefinition, ...] = (
    RowDefinition(
        "total_revenue",
        "Total Revenue",
        "total",
        0,
        None,
        "duration",
        (
            "RevenueFromContractsWithCustomers",
            "Revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "Revenue",
            "SalesRevenueNet",
        ),
    ),
    RowDefinition(
        "cost_of_revenue",
        "Cost of Revenue",
        "line",
        0,
        None,
        "duration",
        ("CostOfSales", "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfSales"),
    ),
    RowDefinition(
        "net_interest_income",
        "Net Interest Income",
        "line",
        0,
        None,
        "duration",
        ("InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss"),
    ),
    RowDefinition(
        "non_interest_income",
        "Non-Interest Income",
        "line",
        0,
        None,
        "duration",
        ("NoninterestIncome", "NoninterestIncomeOther"),
    ),
    RowDefinition(
        "gross_profit",
        "Gross Profit",
        "total",
        0,
        None,
        "duration",
        ("GrossProfit",),
    ),
    RowDefinition(
        "operating_expense",
        "Operating Expense",
        "parent",
        0,
        None,
        "duration",
        ("OperatingExpenseExcludingCostOfSales", "OperatingExpenses"),
    ),
    RowDefinition(
        "research_development",
        "Research and Development",
        "line",
        1,
        "operating_expense",
        "duration",
        (
            "ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentCostsRecognisedAsExpense",
            "ResearchAndDevelopmentExpenseByNature",
            "ResearchExpense",
            "DevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
            "ResearchAndDevelopmentInProcess",
        ),
    ),
    RowDefinition(
        "selling_general_admin",
        "Selling General and Administrative",
        "line",
        1,
        "operating_expense",
        "duration",
        (
            "SellingGeneralAndAdministrativeExpense",
            "SellingAndMarketingExpense",
            "SalesAndMarketingExpense", "AdministrativeExpense"
        ),
    ),
    RowDefinition(
        "operating_income",
        "Operating Income",
        "total",
        0,
        None,
        "duration",
        ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities"),
    ),
    RowDefinition(
        "interest_expense",
        "Interest Expense",
        "line",
        0,
        None,
        "duration",
        ("FinanceCosts", "InterestExpenseNonOperating", "InterestExpense", "FinanceCosts"),
    ),
    RowDefinition(
        "other_income_expense",
        "Other Income / Expense Net",
        "line",
        0,
        None,
        "duration",
        ("OtherOperatingIncomeExpense", "NonoperatingIncomeExpense", "OtherIncomeExpenseNet"),
    ),
    RowDefinition(
        "pretax_income",
        "Pretax Income",
        "total",
        0,
        None,
        "duration",
        (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxes", "ProfitLossBeforeTax"
        ),
    ),
    RowDefinition(
        "tax_provision",
        "Tax Provision",
        "line",
        0,
        None,
        "duration",
        ("IncomeTaxExpenseContinuingOperations", "CurrentTaxExpenseIncome", "IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"),
    ),
    RowDefinition(
        "net_income",
        "Net Income",
        "total",
        0,
        None,
        "duration",
        ("NetIncomeLoss", "ProfitLoss"),
    ),
    RowDefinition(
        "net_income_common",
        "Net Income Available to Common Stockholders",
        "line",
        0,
        None,
        "duration",
        ("NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent", "AccountingProfit"),
    ),
    RowDefinition(
        "basic_eps",
        "Basic EPS",
        "line",
        0,
        None,
        "duration",
        ("EarningsPerShareBasic", "BasicEarningsLossPerShare"),
        ("USD/shares", "pure"),
    ),
    RowDefinition(
        "diluted_eps",
        "Diluted EPS",
        "line",
        0,
        None,
        "duration",
        ("EarningsPerShareDiluted", "DilutedEarningsLossPerShare"),
        ("USD/shares", "pure"),
    ),
    RowDefinition(
        "basic_average_shares",
        "Basic Average Shares",
        "line",
        0,
        None,
        "duration",
        ("WeightedAverageNumberOfSharesOutstandingBasic", "AdjustedWeightedAverageShares"),
        ("shares",),
    ),
    RowDefinition(
        "diluted_average_shares",
        "Diluted Average Shares",
        "line",
        0,
        None,
        "duration",
        ("WeightedAverageNumberOfDilutedSharesOutstanding",),
        ("shares",),
    ),
    RowDefinition(
        "ebit",
        "EBIT",
        "line",
        0,
        None,
        "duration",
        ("EarningsBeforeInterestAndTaxes",),
    ),
    RowDefinition(
        "ebitda",
        "EBITDA",
        "line",
        0,
        None,
        "duration",
        ("EarningsBeforeInterestTaxesDepreciationAndAmortization",),
    ),
    RowDefinition(
        "depreciation_amortization",
        "Reconciled Depreciation",
        "line",
        0,
        None,
        "duration",
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
            "Depreciation",
        ),
    ),
)

BALANCE_ROWS: tuple[RowDefinition, ...] = (
    RowDefinition(
        "cash",
        "Cash and Cash Equivalents",
        "line",
        0,
        None,
        "instant",
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashAndDueFromBanks",
            "CashAndCashEquivalents",
            "Cash",
        ),
    ),
    RowDefinition(
        "marketable_securities_current",
        "Current Marketable Securities",
        "line",
        0,
        None,
        "instant",
        (
            "ShortTermInvestments",
            "MarketableSecuritiesCurrent",
            "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
            "ShorttermInvestmentsClassifiedAsCashEquivalents",
            "CurrentFinancialAssetsAtAmortisedCost",
            "OtherCurrentFinancialAssets",
        ),
    ),
    RowDefinition(
        "marketable_securities_noncurrent",
        "Noncurrent Marketable Securities",
        "line",
        0,
        None,
        "instant",
        (
            "MarketableSecuritiesNoncurrent",
            "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
        ),
    ),
    RowDefinition(
        "marketable_securities",
        "Marketable Securities",
        "derived",
        0,
        None,
        "derived",
    ),
    RowDefinition(
        "receivables",
        "Accounts Receivable",
        "line",
        0,
        None,
        "instant",
        ("AccountsReceivableNetCurrent", "CurrentTradeReceivables"),
    ),
    RowDefinition(
        "inventory",
        "Inventory",
        "line",
        0,
        None,
        "instant",
        ("InventoryNet", "Inventories"),
    ),
    RowDefinition(
        "current_assets",
        "Current Assets",
        "total",
        0,
        None,
        "instant",
        ("AssetsCurrent", "CurrentAssets"),
    ),
    RowDefinition(
        "property_plant_equipment",
        "Net Property, Plant and Equipment",
        "line",
        0,
        None,
        "instant",
        ("PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipment"),
    ),
    RowDefinition(
        "goodwill",
        "Goodwill",
        "line",
        0,
        None,
        "instant",
        ("Goodwill",),
    ),
    RowDefinition(
        "intangible_assets",
        "Intangible Assets Excluding Goodwill",
        "line",
        0,
        None,
        "instant",
        (
            "IntangibleAssetsNetExcludingGoodwill",
            "FiniteLivedIntangibleAssetsNet",
            "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
            "OtherIntangibleAssetsNet",
        ),
    ),
    RowDefinition(
        "total_assets",
        "Total Assets",
        "total",
        0,
        None,
        "instant",
        ("Assets",),
    ),
    RowDefinition(
        "accounts_payable",
        "Accounts Payable",
        "line",
        0,
        None,
        "instant",
        ("AccountsPayableCurrent", "TradeAndOtherCurrentPayablesToTradeSuppliers"),
    ),
    RowDefinition(
        "current_liabilities",
        "Current Liabilities",
        "total",
        0,
        None,
        "instant",
        ("LiabilitiesCurrent", "CurrentLiabilities"),
    ),
    RowDefinition(
        "commercial_paper",
        "Commercial Paper",
        "line",
        0,
        None,
        "instant",
        ("CommercialPaper",),
    ),
    RowDefinition(
        "short_term_borrowings",
        "Short-Term Borrowings",
        "line",
        0,
        None,
        "instant",
        ("ShortTermBorrowings", "ShorttermBorrowings", "ShortTermDebt"),
    ),
    RowDefinition(
        "current_portion_long_term_debt",
        "Current Portion of Long-Term Debt",
        "line",
        0,
        None,
        "instant",
        (
            "LongTermDebtCurrent",
            "ShorttermBorrowings",
            "CurrentPortionOfLongtermBorrowings",
            "CurrentPortionOfLongTermDebt",
            "LongTermDebtAndFinanceLeaseObligationsCurrent",
            "FinanceLeaseLiabilityCurrent",
            "CurrentPortionOfLongtermBorrowings",
            "CurrentLeaseLiabilities",
        ),
    ),
    RowDefinition(
        "short_term_debt",
        "Current Debt",
        "derived",
        0,
        None,
        "derived",
    ),
    RowDefinition(
        "long_term_debt",
        "Long Term Debt",
        "line",
        0,
        None,
        "instant",
        (
            "LongTermDebtNoncurrent",
            "LongTermDebt",
            "LongtermBorrowings",
            "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
            "FinanceLeaseLiabilityNoncurrent",
            "LongtermBorrowings",
            "NoncurrentLeaseLiabilities",
        ),
    ),
    RowDefinition(
        "total_debt",
        "Total Debt",
        "total",
        0,
        None,
        "instant",
        (
            "DebtCurrentAndNoncurrent",
            "DebtAndFinanceLeaseObligations",
            "LongTermDebtAndFinanceLeaseObligations",
            "Borrowings",
            "LeaseLiabilities",
        ),
    ),
    RowDefinition(
        "total_liabilities",
        "Total Liabilities",
        "total",
        0,
        None,
        "instant",
        ("Liabilities",),
    ),
    RowDefinition(
        "retained_earnings",
        "Retained Earnings",
        "line",
        0,
        None,
        "instant",
        ("RetainedEarningsAccumulatedDeficit", "RetainedEarnings"),
    ),
    RowDefinition(
        "stockholders_equity",
        "Stockholders' Equity",
        "total",
        0,
        None,
        "instant",
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "EquityAttributableToOwnersOfParent",
            "Equity",
            "EquityAttributableToOwnersOfParent",
        ),
    ),
    RowDefinition(
        "shares_outstanding",
        "Common Shares Outstanding",
        "line",
        0,
        None,
        "instant",
        ("EntityCommonStockSharesOutstanding",),
        ("shares",),
    ),
)

CASH_FLOW_ROWS: tuple[RowDefinition, ...] = (
    RowDefinition(
        "operating_cash_flow",
        "Operating Cash Flow",
        "total",
        0,
        None,
        "duration",
        ("NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "CashFlowsFromUsedInOperations"),
    ),
    RowDefinition(
        "depreciation_amortization",
        "Depreciation and Amortization",
        "line",
        1,
        "operating_cash_flow",
        "duration",
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
            "Depreciation",
        ),
    ),
    RowDefinition(
        "stock_based_compensation",
        "Stock-Based Compensation",
        "line",
        1,
        "operating_cash_flow",
        "duration",
        ("ShareBasedCompensation",),
    ),
    RowDefinition(
        "change_in_working_capital",
        "Change in Working Capital",
        "line",
        1,
        "operating_cash_flow",
        "duration",
        (
            "IncreaseDecreaseInOperatingCapital",
            "IncreaseDecreaseInOperatingLiabilities",
            "IncreaseDecreaseInOtherOperatingCapitalNet",
        ),
    ),
    RowDefinition(
        "change_in_accounts_receivable",
        "Change in Accounts Receivable",
        "line",
        2,
        "change_in_working_capital",
        "duration",
        ("IncreaseDecreaseInAccountsReceivable",),
    ),
    RowDefinition(
        "change_in_inventories",
        "Change in Inventories",
        "line",
        2,
        "change_in_working_capital",
        "duration",
        ("IncreaseDecreaseInInventories",),
    ),
    RowDefinition(
        "change_in_accounts_payable",
        "Change in Accounts Payable",
        "line",
        2,
        "change_in_working_capital",
        "duration",
        ("IncreaseDecreaseInAccountsPayable",),
    ),
    RowDefinition(
        "change_in_other_operating_assets",
        "Change in Other Operating Assets",
        "line",
        2,
        "change_in_working_capital",
        "duration",
        ("IncreaseDecreaseInOtherOperatingAssets",),
    ),
    RowDefinition(
        "change_in_other_operating_liabilities",
        "Change in Other Operating Liabilities",
        "line",
        2,
        "change_in_working_capital",
        "duration",
        ("IncreaseDecreaseInOtherOperatingLiabilities",),
    ),
    RowDefinition(
        "change_in_other_receivables",
        "Change in Other Receivables",
        "line",
        2,
        "change_in_working_capital",
        "duration",
        ("IncreaseDecreaseInOtherReceivables",),
    ),
    RowDefinition(
        "capital_expenditure",
        "Capital Expenditure",
        "line",
        0,
        None,
        "duration",
        (
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsForProceedsFromOtherPropertyPlantAndEquipment", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"
        ),
    ),
    RowDefinition(
        "free_cash_flow",
        "Free Cash Flow",
        "derived",
        0,
        None,
        "derived",
    ),
    RowDefinition(
        "acquisitions",
        "Acquisitions and Business Combinations",
        "line",
        0,
        None,
        "duration",
        ("PaymentsToAcquireBusinessesNetOfCashAcquired",),
    ),
    RowDefinition(
        "dividends_paid",
        "Dividends Paid",
        "line",
        0,
        None,
        "duration",
        ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
    ),
    RowDefinition(
        "share_repurchases",
        "Share Repurchases",
        "line",
        0,
        None,
        "duration",
        ("PaymentsForRepurchaseOfCommonStock",),
    ),
    RowDefinition(
        "debt_issued",
        "Debt Issued",
        "line",
        0,
        None,
        "duration",
        (
            "ProceedsFromIssuanceOfLongTermDebt",
            "ProceedsFromIssuanceOfDebt",
        ),
    ),
    RowDefinition(
        "debt_repaid",
        "Debt Repaid",
        "line",
        0,
        None,
        "duration",
        ("RepaymentsOfLongTermDebt", "RepaymentsOfDebt"),
    ),
    RowDefinition(
        "financing_cash_flow",
        "Financing Cash Flow",
        "total",
        0,
        None,
        "duration",
        ("NetCashProvidedByUsedInFinancingActivities",),
    ),
    RowDefinition(
        "cash_change",
        "Cash Change",
        "total",
        0,
        None,
        "duration",
        (
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashAndCashEquivalentsPeriodIncreaseDecrease",
        ),
    ),
)

STATEMENT_ROWS: dict[StatementType, tuple[RowDefinition, ...]] = {
    "income": INCOME_ROWS,
    "balance_sheet": BALANCE_ROWS,
    "cash_flow": CASH_FLOW_ROWS,
}


def _select_taxonomy(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    all_facts = payload.get("facts", {})
    us_gaap = all_facts.get("us-gaap", {})
    if us_gaap:
        return "us-gaap", us_gaap
    ifrs = all_facts.get("ifrs-full", {})
    if ifrs:
        return "ifrs-full", ifrs
    return "unavailable", {}


def _concept_units(
    facts: dict[str, Any],
    concepts: tuple[str, ...],
    preferred_units: tuple[str, ...],
) -> list[tuple[dict[str, Any], str, str]]:
    results = []
    for concept in concepts:
        payload = facts.get(concept)
        if not payload:
            continue
        units = payload.get("units", {})
        found = False
        for unit in preferred_units:
            if unit in units:
                for fact in units[unit]:
                    results.append((fact, concept, unit))
                found = True
                break
        
        if not found and "USD" in preferred_units:
            for unit in units:
                if unit not in {"shares", "pure", "USD"}:
                    for fact in units[unit]:
                        results.append((fact, concept, unit))
                    break
    return results

def _cell(
    row: dict[str, Any],
    concept: str,
    unit: str,
    taxonomy: str,
    status: str = "reported",
    basis: str | None = None,
    input_refs: list[str] | None = None,
) -> dict[str, Any]:
    source_fact = {
        "concept": concept,
        "unit": unit,
        "value": row.get("val"),
        "period_start": row.get("start"),
        "period_end": row.get("end"),
        "fiscal_year": row.get("fy"),
        "fiscal_period": row.get("fp"),
        "form": row.get("form"),
        "filed": row.get("filed"),
        "accession": row.get("accn"),
    }
    return {
        "value": row.get("val"),
        "unit": unit,
        "status": status,
        "concept": concept,
        "taxonomy": taxonomy,
        "basis": basis,
        "input_refs": input_refs or [],
        "source_ref": 0,
        "period_start": row.get("start"),
        "period_end": row.get("end"),
        "duration_days": _duration_days(row),
        "fiscal_year": row.get("fy"),
        "fiscal_period": row.get("fp"),
        "form": row.get("form"),
        "filed": row.get("filed"),
        "accession": row.get("accn"),
        "calculation_method": None,
        "source_facts": [source_fact],
        "warnings": [],
        "data_status": status,
    }


def _period_from_cell(
    key: str,
    cell: dict[str, Any],
    statement_period: StatementPeriod,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": _period_label(key, cell, statement_period),
        "period_end": cell.get("period_end"),
        "period_start": cell.get("period_start"),
        "fiscal_period": cell.get("fiscal_period"),
        "statement_period": statement_period,
        "source_ref": cell.get("source_ref"),
    }


def _period_label(
    key: str,
    cell: dict[str, Any],
    statement_period: StatementPeriod,
) -> str:
    if statement_period == "annual":
        end = cell.get("period_end") or key
        return end[:4] if len(end) >= 4 else key
    if key.startswith("CY"):
        return key.replace("CY", "").replace("Q", " Q")
    end = cell.get("period_end")
    return end or key


def _reported_duration_cells(
    facts: dict[str, Any],
    definition: RowDefinition,
    taxonomy: str,
    statement_period: StatementPeriod,
) -> dict[str, dict[str, Any]]:
    matched_facts = _concept_units(
        facts,
        definition.concepts,
        definition.preferred_units,
    )
    if not matched_facts:
        return {}

    cells: dict[str, dict[str, Any]] = {}
    for fact, concept, unit in matched_facts:
        if not fact.get("start") or not fact.get("end"):
            continue
        if statement_period == "annual":
            if fact.get("form") not in ANNUAL_FORMS or fact.get("fp") != "FY":
                continue
            key = fact["end"]
        else:
            frame = fact.get("frame") or ""
            if (
                fact.get("form") not in QUARTERLY_FORMS
                or not frame.startswith("CY")
                or "Q" not in frame
                or not _looks_like_single_quarter(fact)
            ):
                continue
            key = frame
        existing = cells.get(key)
        if existing is None or fact.get("filed", "") > existing.get("filed", ""):
            cells[key] = _cell(fact, concept, unit, taxonomy)
    return cells


def _reported_duration_fact_cells(
    facts: dict[str, Any],
    definition: RowDefinition,
    taxonomy: str,
) -> list[dict[str, Any]]:
    matched_facts = _concept_units(
        facts,
        definition.concepts,
        definition.preferred_units,
    )
    if not matched_facts:
        return []

    cells = []
    for fact, concept, unit in matched_facts:
        if (
            fact.get("form") not in ANNUAL_FORMS | {"10-Q", "6-K"}
            or not fact.get("start")
            or not fact.get("end")
        ):
            continue
        cell = _cell(fact, concept, unit, taxonomy)
        cell["frame"] = fact.get("frame")
        cells.append(cell)
    return cells


def _duration_days(row: dict[str, Any]) -> int | None:
    try:
        start = date.fromisoformat(row["start"])
        end = date.fromisoformat(row["end"])
    except (KeyError, TypeError, ValueError):
        return None
    return (end - start).days + 1


def _looks_like_single_quarter(fact: dict[str, Any]) -> bool:
    try:
        start = date.fromisoformat(fact["start"])
        end = date.fromisoformat(fact["end"])
    except (KeyError, TypeError, ValueError):
        return False
    days = (end - start).days + 1
    return 60 <= days <= 120


def _reported_instant_cells(
    facts: dict[str, Any],
    dei_facts: dict[str, Any],
    definition: RowDefinition,
    taxonomy: str,
    statement_period: StatementPeriod,
) -> dict[str, dict[str, Any]]:
    source_facts = dei_facts if definition.id == "shares_outstanding" else facts
    matched_facts = _concept_units(
        source_facts,
        definition.concepts,
        definition.preferred_units,
    )
    if not matched_facts:
        return {}

    cells: dict[str, dict[str, Any]] = {}
    for fact, concept, unit in matched_facts:
        if fact.get("start") or not fact.get("end"):
            continue
        if statement_period == "annual":
            if fact.get("form") not in ANNUAL_FORMS:
                continue
        elif fact.get("form") not in QUARTERLY_FORMS:
            continue
        key = fact["end"]
        existing = cells.get(key)
        if existing is None or fact.get("filed", "") > existing.get("filed", ""):
            cells[key] = _cell(fact, concept, unit, taxonomy)
    return cells


def _sort_periods(
    periods: dict[str, dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    return sorted(
        periods.values(),
        key=lambda item: item.get("period_end") or item["key"],
        reverse=True,
    )[:limit]


def _empty_cell() -> dict[str, Any]:
    return {
        "value": None,
        "unit": None,
        "status": "unavailable",
        "concept": None,
        "taxonomy": None,
        "basis": None,
        "input_refs": [],
        "source_ref": None,
        "period_start": None,
        "period_end": None,
        "form": None,
        "filed": None,
        "accession": None,
    }


def _build_ttm_cell(
    duration_facts: list[dict[str, Any]],
    standalone_quarter_cells: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    ytd_ttm = _build_ytd_ttm_cell(duration_facts)
    if ytd_ttm is not None:
        return ytd_ttm
    return _build_four_quarter_ttm_cell(standalone_quarter_cells)


def _build_ytd_ttm_cell(duration_facts: list[dict[str, Any]]) -> dict[str, Any] | None:
    annual = _dedupe_duration_cells(
        [
            cell
            for cell in duration_facts
            if cell.get("form") in ANNUAL_FORMS
            and cell.get("fiscal_period") == "FY"
            and _valid_annual_duration(cell)
        ]
    )
    ytd = _dedupe_duration_cells(
        [
            cell
            for cell in duration_facts
            if cell.get("form") in {"10-Q", "6-K"}
            and cell.get("fiscal_period") in {"Q1", "Q2", "Q3"}
            and _valid_ytd_duration(cell)
        ]
    )
    if not annual or not ytd:
        return None

    ytd_sorted = sorted(
        ytd,
        key=lambda cell: (
            cell.get("period_end") or "",
            cell.get("filed") or "",
        ),
        reverse=True,
    )
    for current_ytd in ytd_sorted:
        annual_base = _matching_annual_base(current_ytd, annual)
        prior_ytd = _matching_prior_ytd(current_ytd, ytd)
        if annual_base is None or prior_ytd is None:
            continue
        if not _compatible_ttm_components(annual_base, current_ytd, prior_ytd):
            continue
        value = (
            annual_base["value"]
            + current_ytd["value"]
            - prior_ytd["value"]
        )
        return _derived_ttm_cell(
            value=value,
            method="annual_plus_current_ytd_minus_prior_ytd",
            basis=(
                "latest completed fiscal year + current fiscal-year YTD - "
                "prior-year comparable YTD"
            ),
            period_start=_ttm_start_from_prior_ytd(prior_ytd),
            period_end=current_ytd.get("period_end"),
            components=[
                ("annual_base", annual_base),
                ("current_ytd", current_ytd),
                ("prior_comparable_ytd", prior_ytd),
            ],
            warnings=[],
        )
    return None


def _build_four_quarter_ttm_cell(
    cells: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    reported = [
        (key, cell)
        for key, cell in cells.items()
        if key.startswith("CY") and cell.get("status") == "reported"
    ]
    reported.sort(key=lambda item: item[0], reverse=True)
    latest = reported[:4]
    if len(latest) != 4:
        return None
    units = {cell.get("unit") for _, cell in latest}
    concepts = {cell.get("concept") for _, cell in latest}
    if len(units) != 1 or len(concepts) != 1:
        return None
    values = [cell.get("value") for _, cell in latest]
    if any(value is None for value in values):
        return None
    latest_cell = latest[0][1]
    earliest_cell = latest[-1][1]
    if not _looks_like_ttm_span(earliest_cell, latest_cell):
        return None
    return _derived_ttm_cell(
        value=sum(values),
        method="four_validated_standalone_quarters",
        basis="sum of latest four validated standalone quarterly values",
        period_start=earliest_cell.get("period_start"),
        period_end=latest_cell.get("period_end"),
        components=[(key, cell) for key, cell in latest],
        warnings=[
            "TTM used standalone-quarter fallback because comparable YTD inputs were unavailable."
        ],
    )


def _dedupe_duration_cells(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_period: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = {}
    for cell in cells:
        key = (
            cell.get("period_start"),
            cell.get("period_end"),
            cell.get("fiscal_period"),
        )
        existing = by_period.get(key)
        if existing is None or cell.get("filed", "") > existing.get("filed", ""):
            by_period[key] = cell
    return list(by_period.values())


def _valid_annual_duration(cell: dict[str, Any]) -> bool:
    days = cell.get("duration_days")
    return days is not None and 330 <= days <= 380


def _valid_ytd_duration(cell: dict[str, Any]) -> bool:
    days = cell.get("duration_days")
    fiscal_period = cell.get("fiscal_period")
    if days is None:
        return False
    if fiscal_period == "Q1":
        return 60 <= days <= 120
    if fiscal_period == "Q2":
        return 150 <= days <= 215
    if fiscal_period == "Q3":
        return 240 <= days <= 310
    return False


def _matching_annual_base(
    current_ytd: dict[str, Any],
    annual_cells: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        ytd_start = date.fromisoformat(current_ytd["period_start"])
    except (KeyError, TypeError, ValueError):
        return None
    candidates = []
    for annual in annual_cells:
        try:
            annual_end = date.fromisoformat(annual["period_end"])
        except (KeyError, TypeError, ValueError):
            continue
        distance = abs((ytd_start - annual_end).days)
        if 0 <= (ytd_start - annual_end).days <= 7:
            candidates.append((distance, annual.get("filed", ""), annual))
    if not candidates:
        return None
    closest_distance = min(item[0] for item in candidates)
    closest = [item for item in candidates if item[0] == closest_distance]
    return max(closest, key=lambda item: item[1])[2]


def _matching_prior_ytd(
    current_ytd: dict[str, Any],
    ytd_cells: list[dict[str, Any]],
) -> dict[str, Any] | None:
    current_fp = current_ytd.get("fiscal_period")
    current_days = current_ytd.get("duration_days")
    try:
        current_end = date.fromisoformat(current_ytd["period_end"])
    except (KeyError, TypeError, ValueError):
        return None
    candidates = []
    for prior in ytd_cells:
        if prior is current_ytd or prior.get("fiscal_period") != current_fp:
            continue
        if current_days is None or prior.get("duration_days") is None:
            continue
        if abs(current_days - prior["duration_days"]) > 10:
            continue
        try:
            prior_end = date.fromisoformat(prior["period_end"])
        except (KeyError, TypeError, ValueError):
            continue
        day_gap = (current_end - prior_end).days
        if 350 <= day_gap <= 380:
            candidates.append((abs(day_gap - 365), prior.get("filed", ""), prior))
    if not candidates:
        return None
    closest_gap = min(item[0] for item in candidates)
    closest = [item for item in candidates if item[0] == closest_gap]
    return max(closest, key=lambda item: item[1])[2]


def _compatible_ttm_components(
    annual_base: dict[str, Any],
    current_ytd: dict[str, Any],
    prior_ytd: dict[str, Any],
) -> bool:
    units = {
        annual_base.get("unit"),
        current_ytd.get("unit"),
        prior_ytd.get("unit"),
    }
    concepts = {
        annual_base.get("concept"),
        current_ytd.get("concept"),
        prior_ytd.get("concept"),
    }
    taxonomies = {
        annual_base.get("taxonomy"),
        current_ytd.get("taxonomy"),
        prior_ytd.get("taxonomy"),
    }
    return len(units) == 1 and len(concepts) == 1 and len(taxonomies) == 1


def _ttm_start_from_prior_ytd(prior_ytd: dict[str, Any]) -> str | None:
    try:
        prior_end = date.fromisoformat(prior_ytd["period_end"])
    except (KeyError, TypeError, ValueError):
        return None
    return (prior_end + timedelta(days=1)).isoformat()


def _derived_ttm_cell(
    *,
    value: float | int,
    method: str,
    basis: str,
    period_start: str | None,
    period_end: str | None,
    components: list[tuple[str, dict[str, Any]]],
    warnings: list[str],
) -> dict[str, Any]:
    latest_cell = max(
        (cell for _, cell in components),
        key=lambda cell: (cell.get("period_end") or "", cell.get("filed") or ""),
    )
    return {
        "value": value,
        "unit": latest_cell.get("unit"),
        "status": "derived",
        "concept": latest_cell.get("concept"),
        "taxonomy": latest_cell.get("taxonomy"),
        "basis": basis,
        "input_refs": [label for label, _ in components],
        "source_ref": latest_cell.get("source_ref"),
        "period_start": period_start,
        "period_end": period_end,
        "duration_days": _span_days(period_start, period_end),
        "fiscal_year": latest_cell.get("fiscal_year"),
        "fiscal_period": "TTM",
        "form": latest_cell.get("form"),
        "filed": latest_cell.get("filed"),
        "accession": latest_cell.get("accession"),
        "calculation_method": method,
        "source_facts": [
            {
                "role": label,
                "value": cell.get("value"),
                "unit": cell.get("unit"),
                "concept": cell.get("concept"),
                "taxonomy": cell.get("taxonomy"),
                "period_start": cell.get("period_start"),
                "period_end": cell.get("period_end"),
                "duration_days": cell.get("duration_days"),
                "fiscal_year": cell.get("fiscal_year"),
                "fiscal_period": cell.get("fiscal_period"),
                "form": cell.get("form"),
                "filed": cell.get("filed"),
                "accession": cell.get("accession"),
            }
            for label, cell in components
        ],
        "warnings": warnings,
        "data_status": "calculated",
    }


def _span_days(start_value: str | None, end_value: str | None) -> int | None:
    try:
        start = date.fromisoformat(start_value or "")
        end = date.fromisoformat(end_value or "")
    except ValueError:
        return None
    return (end - start).days


def _looks_like_ttm_span(
    earliest_cell: dict[str, Any],
    latest_cell: dict[str, Any],
) -> bool:
    try:
        start = date.fromisoformat(earliest_cell["period_start"])
        end = date.fromisoformat(latest_cell["period_end"])
    except (KeyError, TypeError, ValueError):
        return False
    days = (end - start).days + 1
    return 330 <= days <= 380


def _derive_total_debt(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    derived = row_by_id.get("total_debt")
    if not derived:
        return
    component_rows = [
        row_by_id.get("commercial_paper"),
        row_by_id.get("short_term_borrowings"),
        row_by_id.get("current_portion_long_term_debt"),
        row_by_id.get("long_term_debt"),
    ]
    keys = sorted(
        {
            key
            for row in component_rows
            if row is not None
            for key, cell in row["cells"].items()
            if cell.get("status") == "reported"
        }
    )
    for key in keys:
        components = [
            (row["id"], row["cells"].get(key))
            for row in component_rows
            if row is not None and row["cells"].get(key)
        ]
        valid = [
            (label, cell)
            for label, cell in components
            if cell
            and cell.get("status") == "reported"
            and cell.get("value") is not None
        ]
        if len(valid) < 2:
            continue
        unit = valid[0][1].get("unit")
        period_end = valid[0][1].get("period_end")
        if any(
            cell.get("unit") != unit or cell.get("period_end") != period_end
            for _, cell in valid
        ):
            continue
        value = sum(cell["value"] for _, cell in valid)
        source_facts = [
            source_fact
            for _, cell in valid
            for source_fact in cell.get("source_facts", [])
        ]
        derived["cells"][key] = {
            **valid[0][1],
            "value": value,
            "status": "derived",
            "concept": None,
            "basis": (
                "sum of reported compatible debt components; unavailable "
                "components are not treated as zero"
            ),
            "input_refs": [cell.get("concept") or label for label, cell in valid],
            "source_facts": source_facts,
        }


def _derive_missing_margins(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    revenue = row_by_id.get("total_revenue")
    cost = row_by_id.get("cost_of_revenue")
    gross = row_by_id.get("gross_profit")
    
    if not revenue:
        return
        
    keys = sorted(set(revenue["cells"].keys()))
    for key in keys:
        rev_cell = revenue["cells"].get(key, {})
        rev_val = rev_cell.get("value")
        if rev_val is None:
            continue
            
        cost_cell = cost["cells"].get(key, {}) if cost else {}
        gross_cell = gross["cells"].get(key, {}) if gross else {}
        cost_val = cost_cell.get("value")
        gross_val = gross_cell.get("value")
        
        if gross_val is not None and cost_val is None and cost:
            derived_cost = rev_val - gross_val
            if derived_cost >= 0:
                cost["cells"][key] = {
                    "value": derived_cost,
                    "status": "derived",
                    "concept": None,
                    "calculation_method": "total_revenue - gross_profit",
                    "basis": "Derived from Total Revenue minus Gross Profit.",
                    "input_refs": [rev_cell.get("concept"), gross_cell.get("concept")]
                }
                
        if cost_val is not None and gross_val is None and gross:
            derived_gross = rev_val - cost_val
            gross["cells"][key] = {
                "value": derived_gross,
                "status": "derived",
                "concept": None,
                "calculation_method": "total_revenue - cost_of_revenue",
                "basis": "Derived from Total Revenue minus Cost of Revenue.",
                "input_refs": [rev_cell.get("concept"), cost_cell.get("concept")]
            }


def _derive_gross_profit_for_banks(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    gross_profit = row_by_id.get("gross_profit")
    nii = row_by_id.get("net_interest_income")
    non_nii = row_by_id.get("non_interest_income")
    
    if not gross_profit or not nii or not non_nii:
        return

    keys = sorted(set(nii["cells"].keys()) | set(non_nii["cells"].keys()))
    for key in keys:
        nii_cell = nii["cells"].get(key, {})
        non_nii_cell = non_nii["cells"].get(key, {})
        
        nii_val = nii_cell.get("value")
        non_nii_val = non_nii_cell.get("value")
        
        if nii_val is not None or non_nii_val is not None:
            total = (nii_val or 0) + (non_nii_val or 0)
            base_cell = nii_cell if nii_val is not None else non_nii_cell
            gross_profit["cells"][key] = {
                **base_cell,
                "value": total,
                "status": "derived",
                "concept": None,
                "basis": "Net Interest Income + Non-Interest Income",
                "input_refs": ["net_interest_income", "non_interest_income"],
            }


def _derive_current_debt(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    derived = row_by_id.get("short_term_debt")
    if not derived:
        return
    component_rows = [
        row_by_id.get("commercial_paper"),
        row_by_id.get("short_term_borrowings"),
        row_by_id.get("current_portion_long_term_debt"),
    ]
    keys = sorted(
        {
            key
            for row in component_rows
            if row is not None
            for key, cell in row["cells"].items()
            if cell.get("status") == "reported"
        }
    )
    for key in keys:
        valid = [
            (row["id"], row["cells"][key])
            for row in component_rows
            if row is not None
            and key in row["cells"]
            and row["cells"][key].get("status") == "reported"
            and row["cells"][key].get("value") is not None
        ]
        if not valid:
            continue
        unit = valid[0][1].get("unit")
        period_end = valid[0][1].get("period_end")
        if any(
            cell.get("unit") != unit or cell.get("period_end") != period_end
            for _, cell in valid
        ):
            continue
        source_facts = [
            source_fact
            for _, cell in valid
            for source_fact in cell.get("source_facts", [])
        ]
        derived["cells"][key] = {
            **valid[0][1],
            "value": sum(cell["value"] for _, cell in valid),
            "status": "derived",
            "concept": None,
            "basis": (
                "sum of reported compatible current debt components; unavailable "
                "components are not treated as zero"
            ),
            "input_refs": [cell.get("concept") or label for label, cell in valid],
            "source_facts": source_facts,
        }


def _derive_marketable_securities(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    derived = row_by_id.get("marketable_securities")
    current = row_by_id.get("marketable_securities_current")
    noncurrent = row_by_id.get("marketable_securities_noncurrent")
    if not derived:
        return
    component_rows = [current, noncurrent]
    keys = sorted(
        {
            key
            for row in component_rows
            if row is not None
            for key, cell in row["cells"].items()
            if cell.get("status") == "reported"
        }
    )
    for key in keys:
        valid = [
            (row["id"], row["cells"][key])
            for row in component_rows
            if row is not None
            and key in row["cells"]
            and row["cells"][key].get("status") == "reported"
            and row["cells"][key].get("value") is not None
        ]
        if not valid:
            continue
        unit = valid[0][1].get("unit")
        period_end = valid[0][1].get("period_end")
        if any(
            cell.get("unit") != unit or cell.get("period_end") != period_end
            for _, cell in valid
        ):
            continue
        source_facts = [
            source_fact
            for _, cell in valid
            for source_fact in cell.get("source_facts", [])
        ]
        derived["cells"][key] = {
            **valid[0][1],
            "value": sum(cell["value"] for _, cell in valid),
            "status": "derived",
            "concept": None,
            "basis": (
                "current marketable securities + noncurrent marketable securities; "
                "unavailable components are not treated as zero"
            ),
            "input_refs": [cell.get("concept") or label for label, cell in valid],
            "source_facts": source_facts,
        }


def _derive_free_cash_flow(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    derived = row_by_id.get("free_cash_flow")
    operating = row_by_id.get("operating_cash_flow")
    capex = row_by_id.get("capital_expenditure")
    if not derived or not operating or not capex:
        return
    for key, operating_cell in operating["cells"].items():
        capex_cell = capex["cells"].get(key)
        if (
            capex_cell is None
            or operating_cell.get("status") not in {"reported", "derived"}
            or capex_cell.get("status") not in {"reported", "derived"}
            or operating_cell.get("unit") != capex_cell.get("unit")
        ):
            continue
        derived["cells"][key] = {
            **operating_cell,
            "value": operating_cell["value"] - abs(capex_cell["value"]),
            "status": "derived",
            "concept": None,
            "basis": "operating cash flow - capital expenditure",
            "input_refs": [
                operating_cell.get("concept") or "operating_cash_flow",
                capex_cell.get("concept") or "capital_expenditure",
            ],
        }


def _derive_change_in_working_capital(rows: list[dict[str, Any]]) -> None:
    row_by_id = {row["id"]: row for row in rows}
    derived = row_by_id.get("change_in_working_capital")
    if not derived:
        return

    component_ids = [
        "change_in_accounts_receivable",
        "change_in_inventories",
        "change_in_accounts_payable",
        "change_in_other_operating_assets",
        "change_in_other_operating_liabilities",
        "change_in_other_receivables",
    ]
    component_rows = [
        row_by_id[cid]
        for cid in component_ids
        if cid in row_by_id
    ]
    if not component_rows:
        return

    all_keys: set[str] = set()
    for comp_row in component_rows:
        for key, cell in comp_row["cells"].items():
            if cell.get("status") in {"reported", "derived"} and cell.get("value") is not None:
                all_keys.add(key)

    for key in all_keys:
        existing = derived["cells"].get(key)
        if existing and existing.get("status") in {"reported", "derived"}:
            continue

        total = 0
        input_refs = []
        source_cell = None
        components_found = 0
        for comp_row in component_rows:
            cell = comp_row["cells"].get(key)
            if cell and cell.get("status") in {"reported", "derived"} and cell.get("value") is not None:
                total += cell["value"]
                input_refs.append(cell.get("concept") or comp_row["id"])
                components_found += 1
                if source_cell is None:
                    source_cell = cell

        if components_found < 2 or source_cell is None:
            continue

        derived["cells"][key] = {
            **source_cell,
            "value": total,
            "status": "derived",
            "concept": None,
            "calculation_method": "sum_of_components",
            "basis": "Sum of reported changes in operating assets and liabilities.",
            "input_refs": input_refs,
        }


def _build_statement(
    payload: dict[str, Any],
    statement: StatementType,
    statement_period: StatementPeriod,
    is_bank: bool = False,
) -> dict[str, Any]:
    taxonomy, facts = _select_taxonomy(payload)
    dei_facts = payload.get("facts", {}).get("dei", {})
    definitions = STATEMENT_ROWS[statement]
    rows: list[dict[str, Any]] = []
    discovered_periods: dict[str, dict[str, Any]] = {}

    for definition in definitions:
        if definition.period_kind == "duration":
            cells = _reported_duration_cells(
                facts,
                definition,
                taxonomy,
                statement_period,
            )
        elif definition.period_kind == "instant":
            cells = _reported_instant_cells(
                facts,
                dei_facts,
                definition,
                taxonomy,
                statement_period,
            )
        else:
            cells = {}

        if (
            statement_period == "annual"
            and definition.period_kind == "duration"
            and statement != "balance_sheet"
        ):
            duration_facts = _reported_duration_fact_cells(
                facts,
                definition,
                taxonomy,
            )
            quarterly_cells = _reported_duration_cells(
                facts,
                definition,
                taxonomy,
                "quarterly",
            )
            ttm = _build_ttm_cell(duration_facts, quarterly_cells)
            if ttm is not None:
                cells = {"ttm": ttm, **cells}

        row = {
            "id": definition.id,
            "label": definition.label,
            "depth": definition.depth,
            "kind": definition.kind,
            "parent_id": definition.parent_id,
            "cells": cells,
        }
        rows.append(row)
        for key, cell in cells.items():
            if key == "ttm":
                discovered_periods[key] = {
                    "key": "ttm",
                    "label": "TTM",
                    "period_end": cell.get("period_end"),
                    "period_start": cell.get("period_start"),
                    "fiscal_period": None,
                    "statement_period": "ttm",
                    "source_ref": cell.get("source_ref"),
                }
            else:
                discovered_periods[key] = _period_from_cell(
                    key,
                    cell,
                    statement_period,
                )

    _derive_current_debt(rows)
    _derive_total_debt(rows)
    _derive_marketable_securities(rows)
    _derive_free_cash_flow(rows)
    _derive_change_in_working_capital(rows)
    
    _derive_missing_margins(rows)
    if is_bank:
        _derive_gross_profit_for_banks(rows)
        
    for row in rows:
        for key, cell in row["cells"].items():
            if key in discovered_periods:
                continue
            if key == "ttm":
                discovered_periods[key] = {
                    "key": "ttm",
                    "label": "TTM",
                    "period_end": cell.get("period_end"),
                    "period_start": cell.get("period_start"),
                    "fiscal_period": None,
                    "statement_period": "ttm",
                    "source_ref": cell.get("source_ref"),
                }
            else:
                discovered_periods[key] = _period_from_cell(
                    key,
                    cell,
                    statement_period,
                )

    period_counts: dict[str, int] = {}
    for row in rows:
        for key in row["cells"]:
            period_counts[key] = period_counts.get(key, 0) + 1

    valid_discovered = {
        k: v for k, v in discovered_periods.items()
        if k == "ttm" or period_counts.get(k, 0) >= 3
    }

    ttm_period = valid_discovered.pop("ttm", None)
    limit = 5 if statement_period == "annual" else 12
    periods = _sort_periods(valid_discovered, limit)
    if ttm_period is not None and statement in {"income", "cash_flow"}:
        periods = [ttm_period, *periods[:4]]

    period_keys = [period["key"] for period in periods]
    for row in rows:
        aligned_cells = {}
        for pkey in period_keys:
            if pkey in row["cells"]:
                aligned_cells[pkey] = row["cells"][pkey]
            else:
                closest_key = None
                closest_dist = 45
                if "-" in pkey and len(pkey) == 10:
                    try:
                        target_date = date.fromisoformat(pkey)
                        for ckey in row["cells"]:
                            if "-" in ckey and len(ckey) == 10:
                                cdate = date.fromisoformat(ckey)
                                dist = abs((cdate - target_date).days)
                                if dist < closest_dist:
                                    closest_dist = dist
                                    closest_key = ckey
                    except ValueError:
                        pass
                if closest_key:
                    aligned_cells[pkey] = row["cells"][closest_key]
                else:
                    aligned_cells[pkey] = _empty_cell()
        row["cells"] = aligned_cells

    reported_cells = [
        cell
        for row in rows
        for cell in row["cells"].values()
        if cell.get("status") in {"reported", "derived"}
    ]
    currency_units = [cell.get("unit") for cell in reported_cells
                      if isinstance(cell.get("unit"), str) and len(cell["unit"]) == 3
                      and cell["unit"].isalpha() and cell["unit"].isupper()]
    currency = max(set(currency_units), key=currency_units.count) if currency_units else None
    notes = [
        "Values come from SEC Company Facts and retain reported concept metadata.",
        "Unavailable cells are not converted to zero.",
    ]
    if statement in {"income", "cash_flow"} and ttm_period is None:
        notes.append(
            "TTM is shown only when comparable SEC YTD periods or four "
            "validated standalone quarters exist."
        )

    return {
        "company_name": payload.get("entityName"),
        "statement": statement,
        "period": statement_period,
        "currency": currency,
        "unit_label": "All numbers in raw SEC units; USD statement amounts are not rescaled.",
        "taxonomy": taxonomy,
        "periods": periods,
        "rows": rows,
        "notes": notes,
    }


def extract_financial_statements(payload: dict[str, Any], is_bank: bool = False) -> dict[str, Any]:
    return {
        period: {
            statement: _build_statement(payload, statement, period, is_bank=is_bank)
            for statement in ("income", "balance_sheet", "cash_flow")
        }
        for period in ("annual", "quarterly")
    }
