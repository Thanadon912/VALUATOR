from __future__ import annotations

import re
from typing import Any

from app.providers.sec_capital_allocation import _filing_url
from app.providers.sec_supply_chain import _FilingTextParser, _normalize_text


EQUITY_ISSUANCE_CONCEPTS = (
    "ProceedsFromIssuanceOfCommonStock",
    "ProceedsFromStockOptionsExercised",
    "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans",
)

DEBT_NOTE_PATTERN = re.compile(
    r"\b(?:debt|borrowings?|senior notes?|credit facilit(?:y|ies)|"
    r"liquidity and capital resources|interest expense|maturit(?:y|ies))\b",
    re.I,
)
SHARE_NOTE_PATTERN = re.compile(
    r"\b(?:share repurchases?|stock[- ]based compensation|share[- ]based "
    r"compensation|diluted shares?|basic shares?|equity awards?|shares "
    r"outstanding|equity issuance)\b",
    re.I,
)
MONEY_PATTERN = r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million|thousand)?"
MATURITY_PATTERNS = (
    re.compile(
        MONEY_PATTERN
        + r"[^.;]{0,100}\b(?:matur(?:e|es|ing|ities)|due|payable)"
        + r"[^.;]{0,100}\b(20\d{2})\b",
        re.I,
    ),
    re.compile(
        r"\b(20\d{2})\b[^.;]{0,100}\b(?:matur(?:e|es|ing|ities)|due|payable)"
        + r"[^.;]{0,100}"
        + MONEY_PATTERN,
        re.I,
    ),
)
CREDIT_RATING_PATTERN = re.compile(
    r"\b(S&P|Standard & Poor'?s|Moody'?s|Fitch)\b[^.;]{0,80}?"
    r"\b(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?|CC|C|D|"
    r"Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|B[1-3]|Caa[1-3]|Ca|C)\b",
    re.I,
)


def _empty_debt_profile() -> dict[str, Any]:
    return {
        "short_term_debt": None,
        "long_term_debt": None,
        "total_debt": None,
        "cash_and_equivalents": None,
        "net_debt": None,
        "interest_expense": None,
        "debt_issuance": None,
        "debt_repayment": None,
        "debt_maturities": [],
        "credit_rating": None,
        "debt_to_equity": None,
        "debt_to_assets": None,
        "interest_coverage": None,
        "net_debt_to_operating_cash_flow": None,
        "sources": {},
        "calculation_basis": {},
        "notes": [],
    }


def _empty_share_dilution() -> dict[str, Any]:
    return {
        "basic_shares": None,
        "diluted_shares": None,
        "shares_outstanding": None,
        "weighted_average_shares": None,
        "stock_based_compensation": None,
        "share_repurchases": None,
        "equity_issuance": None,
        "net_share_change_percent": None,
        "dilution_risk": None,
        "diluted_vs_basic_spread_percent": None,
        "year_over_year_basic_share_change_percent": None,
        "year_over_year_diluted_share_change_percent": None,
        "buyback_offset": None,
        "sources": {},
        "calculation_basis": {},
        "notes": [],
    }


def _rows(statement: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        row.get("id"): row
        for row in (statement or {}).get("rows", [])
        if row.get("id")
    }


def _period_keys(statement: dict[str, Any] | None) -> list[str]:
    return [
        period["key"]
        for period in (statement or {}).get("periods", [])
        if period.get("key") and period.get("key") != "ttm"
    ]


def _latest_period_key(statement: dict[str, Any] | None) -> str | None:
    keys = _period_keys(statement)
    return keys[0] if keys else None


def _cell(
    statement: dict[str, Any] | None,
    row_id: str,
    period_key: str | None = None,
) -> dict[str, Any] | None:
    if period_key is None:
        period_key = _latest_period_key(statement)
    if period_key is None:
        return None
    row = _rows(statement).get(row_id)
    if row is None:
        return None
    cell = row.get("cells", {}).get(period_key)
    if not cell or cell.get("status") not in {"reported", "derived"}:
        return None
    if not isinstance(cell.get("value"), (int, float)):
        return None
    return cell


def _value(
    statement: dict[str, Any] | None,
    row_id: str,
    period_key: str | None = None,
) -> float | int | None:
    cell = _cell(statement, row_id, period_key)
    return cell.get("value") if cell else None


def _cell_source(
    cell: dict[str, Any],
    *,
    cik: str,
    label: str,
) -> dict[str, Any]:
    accession = cell.get("accession") or ""
    concept = cell.get("concept") or label
    unit = cell.get("unit") or ""
    return {
        "source_form": cell.get("form"),
        "source_accession": accession,
        "source_url": _filing_url(cik, accession) if accession else "",
        "filing_date": cell.get("filed"),
        "report_date": cell.get("period_end"),
        "section": "sec_xbrl_companyfacts",
        "evidence": (
            f"SEC XBRL fact {concept} reported {cell.get('value')} {unit} "
            f"for period ending {cell.get('period_end')}."
        ),
    }


def _add_source(
    container: dict[str, Any],
    field: str,
    source: dict[str, Any] | None,
) -> None:
    if source is None:
        return
    container.setdefault("sources", {}).setdefault(field, []).append(source)


def _amount_from_capital_metric(
    capital_allocation: dict[str, Any] | None,
    metric: str,
) -> tuple[float | int | None, list[dict[str, Any]]]:
    metric_payload = (
        (capital_allocation or {})
        .get("capital_allocation", {})
        .get(metric, {})
    )
    if metric_payload.get("status") != "reported":
        return None, []
    amount = metric_payload.get("amount")
    if not isinstance(amount, (int, float)):
        return None, []
    return amount, list(metric_payload.get("sources") or [])


def _cash_flow_amount(
    cash_flow: dict[str, Any] | None,
    row_id: str,
    *,
    cik: str,
    positive_outflow: bool = False,
) -> tuple[float | int | None, list[dict[str, Any]]]:
    cell = _cell(cash_flow, row_id)
    if cell is None:
        return None, []
    value = cell["value"]
    if positive_outflow:
        value = abs(value)
    return value, [_cell_source(cell, cik=cik, label=row_id)]


def _safe_ratio(
    numerator: float | int | None,
    denominator: float | int | None,
) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), 4)


def _safe_percent_change(
    current: float | int | None,
    previous: float | int | None,
) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((float(current) - float(previous)) / float(previous) * 100, 4)


def _amount_from_match(match: re.Match[str], amount_index: int) -> int:
    value = float(match.group(amount_index))
    scale = (match.group(amount_index + 1) or "").lower()
    multiplier = 1
    if scale == "billion":
        multiplier = 1_000_000_000
    elif scale == "million":
        multiplier = 1_000_000
    elif scale == "thousand":
        multiplier = 1_000
    return int(round(value * multiplier))


def _filing_passages(
    filings: list[dict[str, str]],
    pattern: re.Pattern[str],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for filing in filings:
        if filing.get("form") not in {"10-K", "10-Q", "20-F", "40-F"}:
            continue
        parser = _FilingTextParser()
        parser.feed(filing.get("html", ""))
        parser.close()
        for block in parser.blocks:
            evidence = _normalize_text(block)
            if not 35 <= len(evidence) <= 1200 or not pattern.search(evidence):
                continue
            key = (filing.get("accession", ""), evidence)
            if key in seen:
                continue
            seen.add(key)
            passages.append(
                {
                    "source_form": filing.get("form"),
                    "source_accession": filing.get("accession"),
                    "source_url": filing.get("source_url"),
                    "filing_date": filing.get("filing_date") or None,
                    "report_date": filing.get("report_date") or None,
                    "section": "filing_text",
                    "evidence": evidence,
                }
            )
            if len(passages) >= limit:
                return passages
    return passages


def _debt_maturities(filings: list[dict[str, str]]) -> list[dict[str, Any]]:
    maturities: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for passage in _filing_passages(filings, DEBT_NOTE_PATTERN, limit=12):
        evidence = passage["evidence"]
        for pattern in MATURITY_PATTERNS:
            for match in pattern.finditer(evidence):
                if pattern is MATURITY_PATTERNS[0]:
                    amount = _amount_from_match(match, 1)
                    year = int(match.group(3))
                else:
                    year = int(match.group(1))
                    amount = _amount_from_match(match, 2)
                key = (year, amount, passage["source_accession"] or "")
                if key in seen:
                    continue
                seen.add(key)
                maturities.append(
                    {
                        "year": year,
                        "amount": amount,
                        "evidence": evidence,
                        "source_url": passage["source_url"],
                        "filing_date": passage["filing_date"],
                    }
                )
    return sorted(maturities, key=lambda item: (item["year"], item["amount"]))


def _credit_rating(filings: list[dict[str, str]]) -> dict[str, Any] | None:
    for passage in _filing_passages(filings, DEBT_NOTE_PATTERN, limit=8):
        match = CREDIT_RATING_PATTERN.search(passage["evidence"])
        if match:
            return {
                "agency": match.group(1),
                "rating": match.group(2),
                "evidence": passage["evidence"],
                "source_url": passage["source_url"],
                "filing_date": passage["filing_date"],
            }
    return None


def _select_duration_fact(
    companyfacts: dict[str, Any] | None,
    concepts: tuple[str, ...],
    *,
    latest_accession: str | None,
) -> tuple[dict[str, Any], str] | None:
    if not companyfacts or latest_accession is None:
        return None
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        facts = us_gaap.get(concept, {}).get("units", {}).get("USD", [])
        candidates = [
            fact
            for fact in facts
            if fact.get("accn") == latest_accession
            and fact.get("form") in {"10-K", "10-Q"}
            and fact.get("start")
            and fact.get("end")
            and isinstance(fact.get("val"), (int, float))
        ]
        if not candidates:
            continue
        selected = max(candidates, key=lambda fact: fact.get("filed", ""))
        return selected, concept
    return None


def _fact_source(
    fact: dict[str, Any],
    *,
    cik: str,
    concept: str,
) -> dict[str, Any]:
    accession = str(fact.get("accn") or "")
    return {
        "source_form": fact.get("form"),
        "source_accession": accession,
        "source_url": _filing_url(cik, accession) if accession else "",
        "filing_date": fact.get("filed"),
        "report_date": fact.get("end"),
        "section": "sec_xbrl_companyfacts",
        "evidence": (
            f"SEC XBRL fact {concept} reported {fact.get('val')} USD "
            f"for {fact.get('start')} through {fact.get('end')}."
        ),
    }


def _equity_issuance(
    companyfacts: dict[str, Any] | None,
    filings: list[dict[str, str]],
    *,
    cik: str,
) -> tuple[float | int | None, list[dict[str, Any]]]:
    latest = next(
        (
            filing
            for filing in filings
            if filing.get("form") in {"10-K", "10-Q"}
            and filing.get("accession")
        ),
        None,
    )
    selection = _select_duration_fact(
        companyfacts,
        EQUITY_ISSUANCE_CONCEPTS,
        latest_accession=latest.get("accession") if latest else None,
    )
    if selection is None:
        return None, []
    fact, concept = selection
    return fact["val"], [_fact_source(fact, cik=cik, concept=concept)]


def _dilution_risk(change_percent: float | None) -> str | None:
    if change_percent is None:
        return None
    if change_percent <= 1:
        return "low"
    if change_percent <= 5:
        return "medium"
    return "high"


def _confidence(data: dict[str, Any], fields: tuple[str, ...]) -> str:
    present = sum(data.get(field) is not None for field in fields)
    if present >= max(1, len(fields) - 1):
        return "high"
    if present >= 3:
        return "medium"
    if present:
        return "low"
    return "low"


def _fiscal_year(
    financial_statements: dict[str, Any],
    filings: list[dict[str, str]],
) -> int | None:
    annual = next(
        (
            filing
            for filing in filings
            if filing.get("form") in {"10-K", "20-F", "40-F"}
            and filing.get("report_date")
        ),
        None,
    )
    if annual:
        try:
            return int(annual["report_date"][:4])
        except (TypeError, ValueError):
            pass
    balance_key = _latest_period_key(
        financial_statements.get("annual", {}).get("balance_sheet")
    )
    if balance_key:
        try:
            return int(balance_key[:4])
        except ValueError:
            return None
    return None


def extract_debt_share_analysis(
    ticker: str,
    financial_statements: dict[str, Any],
    capital_allocation: dict[str, Any] | None,
    filings: list[dict[str, str]],
    *,
    cik: str,
    companyfacts: dict[str, Any] | None = None,
    is_bank: bool = False,
) -> dict[str, Any]:
    annual = financial_statements.get("annual", {})
    income = annual.get("income")
    balance = annual.get("balance_sheet")
    cash_flow = annual.get("cash_flow")
    balance_key = _latest_period_key(balance)
    income_key = (
        balance_key
        if balance_key in _period_keys(income)
        else _latest_period_key(income)
    )
    cash_flow_key = (
        balance_key
        if balance_key in _period_keys(cash_flow)
        else _latest_period_key(cash_flow)
    )

    debt = _empty_debt_profile()
    share = _empty_share_dilution()

    debt_field_rows = {
        "short_term_debt": "short_term_debt",
        "long_term_debt": "long_term_debt",
        "cash_and_equivalents": "cash",
    }
    for field, row_id in debt_field_rows.items():
        cell = _cell(balance, row_id, balance_key)
        if cell:
            debt[field] = cell["value"]
            _add_source(debt, field, _cell_source(cell, cik=cik, label=row_id))

    total_debt_cell = _cell(balance, "total_debt", balance_key)
    if total_debt_cell:
        debt["total_debt"] = total_debt_cell["value"]
        _add_source(
            debt,
            "total_debt",
            _cell_source(total_debt_cell, cik=cik, label="total_debt"),
        )
    elif (
        debt["short_term_debt"] is not None
        and debt["long_term_debt"] is not None
    ):
        debt["total_debt"] = debt["short_term_debt"] + debt["long_term_debt"]
        debt["calculation_basis"]["total_debt"] = (
            "short_term_debt + long_term_debt"
        )
    
    equity = _value(balance, "stockholders_equity", balance_key)
    assets = _value(balance, "total_assets", balance_key)

    if is_bank and debt["total_debt"] is None:
        if assets is not None and equity is not None:
            debt["total_debt"] = assets - equity
            debt["calculation_basis"]["total_debt"] = "estimated from Assets - Equity (Equity Multiplier fallback) for banks"

    interest_cell = _cell(income, "interest_expense", income_key)
    if interest_cell:
        debt["interest_expense"] = interest_cell["value"]
        _add_source(
            debt,
            "interest_expense",
            _cell_source(interest_cell, cik=cik, label="interest_expense"),
        )

    debt_issuance, debt_issuance_sources = _amount_from_capital_metric(
        capital_allocation,
        "debt_issuance",
    )
    if debt_issuance is None:
        debt_issuance, debt_issuance_sources = _cash_flow_amount(
            cash_flow,
            "debt_issued",
            cik=cik,
        )
    debt["debt_issuance"] = debt_issuance
    for source in debt_issuance_sources:
        _add_source(debt, "debt_issuance", source)

    debt_repayment, debt_repayment_sources = _amount_from_capital_metric(
        capital_allocation,
        "debt_repayment",
    )
    if debt_repayment is None:
        debt_repayment, debt_repayment_sources = _cash_flow_amount(
            cash_flow,
            "debt_repaid",
            cik=cik,
            positive_outflow=True,
        )
    debt["debt_repayment"] = debt_repayment
    for source in debt_repayment_sources:
        _add_source(debt, "debt_repayment", source)

    if debt["total_debt"] is not None and debt["cash_and_equivalents"] is not None:
        debt["net_debt"] = debt["total_debt"] - debt["cash_and_equivalents"]
        debt["calculation_basis"]["net_debt"] = (
            "total_debt - cash_and_equivalents"
        )

    operating_income = _value(income, "operating_income", income_key)
    ebit = _value(income, "ebit", income_key)
    operating_cash_flow = _value(cash_flow, "operating_cash_flow", cash_flow_key)
    debt["debt_to_equity"] = _safe_ratio(debt["total_debt"], equity)
    debt["debt_to_assets"] = _safe_ratio(debt["total_debt"], assets)
    debt["interest_coverage"] = _safe_ratio(
        ebit if ebit is not None else operating_income,
        (
            abs(debt["interest_expense"])
            if debt["interest_expense"] is not None
            else None
        ),
    )
    debt["net_debt_to_operating_cash_flow"] = _safe_ratio(
        debt["net_debt"],
        operating_cash_flow,
    )
    if debt["debt_to_equity"] is not None:
        debt["calculation_basis"]["debt_to_equity"] = (
            "total_debt / stockholders_equity"
        )
    if debt["debt_to_assets"] is not None:
        debt["calculation_basis"]["debt_to_assets"] = "total_debt / total_assets"
    if debt["interest_coverage"] is not None:
        debt["calculation_basis"]["interest_coverage"] = (
            "EBIT or operating_income / absolute interest_expense"
        )
    if debt["net_debt_to_operating_cash_flow"] is not None:
        debt["calculation_basis"]["net_debt_to_operating_cash_flow"] = (
            "net_debt / operating_cash_flow"
        )
    debt["debt_maturities"] = _debt_maturities(filings)
    debt["credit_rating"] = _credit_rating(filings)
    debt["notes"] = _filing_passages(filings, DEBT_NOTE_PATTERN)

    basic_cell = _cell(income, "basic_average_shares", income_key)
    diluted_cell = _cell(income, "diluted_average_shares", income_key)
    outstanding_cell = _cell(balance, "shares_outstanding", balance_key)
    if basic_cell:
        share["basic_shares"] = basic_cell["value"]
        _add_source(
            share,
            "basic_shares",
            _cell_source(basic_cell, cik=cik, label="basic_average_shares"),
        )
    if diluted_cell:
        share["diluted_shares"] = diluted_cell["value"]
        _add_source(
            share,
            "diluted_shares",
            _cell_source(diluted_cell, cik=cik, label="diluted_average_shares"),
        )
    if outstanding_cell:
        share["shares_outstanding"] = outstanding_cell["value"]
        _add_source(
            share,
            "shares_outstanding",
            _cell_source(outstanding_cell, cik=cik, label="shares_outstanding"),
        )
    share["weighted_average_shares"] = (
        share["diluted_shares"]
        if share["diluted_shares"] is not None
        else share["basic_shares"]
    )
    if share["weighted_average_shares"] is not None:
        share["calculation_basis"]["weighted_average_shares"] = (
            "diluted weighted-average shares, falling back to basic only when diluted is unavailable"
        )

    stock_comp, stock_comp_sources = _amount_from_capital_metric(
        capital_allocation,
        "equity_compensation",
    )
    if stock_comp is None:
        stock_comp, stock_comp_sources = _cash_flow_amount(
            cash_flow,
            "stock_based_compensation",
            cik=cik,
        )
    share["stock_based_compensation"] = stock_comp
    for source in stock_comp_sources:
        _add_source(share, "stock_based_compensation", source)

    buybacks, buyback_sources = _amount_from_capital_metric(
        capital_allocation,
        "buybacks",
    )
    if buybacks is None:
        buybacks, buyback_sources = _cash_flow_amount(
            cash_flow,
            "share_repurchases",
            cik=cik,
            positive_outflow=True,
        )
    share["share_repurchases"] = buybacks
    for source in buyback_sources:
        _add_source(share, "share_repurchases", source)

    equity_issuance, equity_sources = _equity_issuance(
        companyfacts,
        filings,
        cik=cik,
    )
    share["equity_issuance"] = equity_issuance
    for source in equity_sources:
        _add_source(share, "equity_issuance", source)

    if share["basic_shares"] is not None and share["diluted_shares"] is not None:
        share["diluted_vs_basic_spread_percent"] = _safe_percent_change(
            share["diluted_shares"],
            share["basic_shares"],
        )
        share["calculation_basis"]["diluted_vs_basic_spread_percent"] = (
            "(diluted_shares - basic_shares) / basic_shares * 100"
        )

    income_keys = _period_keys(income)
    if len(income_keys) >= 2:
        current_key, prior_key = income_keys[0], income_keys[1]
        share["year_over_year_basic_share_change_percent"] = (
            _safe_percent_change(
                _value(income, "basic_average_shares", current_key),
                _value(income, "basic_average_shares", prior_key),
            )
        )
        share["year_over_year_diluted_share_change_percent"] = (
            _safe_percent_change(
                _value(income, "diluted_average_shares", current_key),
                _value(income, "diluted_average_shares", prior_key),
            )
        )
        if share["year_over_year_basic_share_change_percent"] is not None:
            share["calculation_basis"][
                "year_over_year_basic_share_change_percent"
            ] = "annual weighted-average basic shares year-over-year change"
        if share["year_over_year_diluted_share_change_percent"] is not None:
            share["calculation_basis"][
                "year_over_year_diluted_share_change_percent"
            ] = "annual weighted-average diluted shares year-over-year change"

    share["net_share_change_percent"] = (
        share["year_over_year_diluted_share_change_percent"]
        if share["year_over_year_diluted_share_change_percent"] is not None
        else share["year_over_year_basic_share_change_percent"]
    )
    if share["net_share_change_percent"] is not None:
        share["calculation_basis"]["net_share_change_percent"] = (
            "year-over-year diluted weighted-average share change, falling back to basic weighted-average share change"
        )
    else:
        point_in_time_change = (
            (capital_allocation or {})
            .get("capital_allocation", {})
            .get("share_dilution", {})
            .get("shares_change_percent")
        )
        if isinstance(point_in_time_change, (int, float)):
            share["net_share_change_percent"] = point_in_time_change
            share["calculation_basis"]["net_share_change_percent"] = (
                "point-in-time common shares outstanding change from capital allocation; not mixed with weighted-average shares"
            )

    if buybacks is not None and stock_comp not in (None, 0):
        share["buyback_offset"] = {
            "share_repurchases": buybacks,
            "stock_based_compensation": stock_comp,
            "offset_amount": buybacks - stock_comp,
            "offset_ratio": round(float(buybacks) / float(stock_comp), 4),
        }
        share["calculation_basis"]["buyback_offset"] = (
            "share_repurchases compared with stock_based_compensation"
        )

    share["dilution_risk"] = _dilution_risk(share["net_share_change_percent"])
    if share["dilution_risk"] is not None:
        share["calculation_basis"]["dilution_risk"] = (
            "low <= 1% net share growth, medium <= 5%, high > 5%"
        )
    share["notes"] = _filing_passages(filings, SHARE_NOTE_PATTERN)

    return {
        "ticker": ticker,
        "fiscal_year": _fiscal_year(financial_statements, filings),
        "debt_profile": debt,
        "share_dilution": share,
        "confidence": {
            "debt_profile": _confidence(
                debt,
                (
                    "short_term_debt",
                    "long_term_debt",
                    "total_debt",
                    "cash_and_equivalents",
                    "interest_expense",
                    "debt_issuance",
                    "debt_repayment",
                ),
            ),
            "share_dilution": _confidence(
                share,
                (
                    "basic_shares",
                    "diluted_shares",
                    "weighted_average_shares",
                    "stock_based_compensation",
                    "share_repurchases",
                    "net_share_change_percent",
                ),
            ),
        },
    }
