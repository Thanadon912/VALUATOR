from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.providers.sec_supply_chain import _FilingTextParser, _normalize_text


SEC_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/"
    "{accession}-index.html"
)

CAPITAL_ALLOCATION_CONCEPTS = {
    "buybacks": (
        "IncreaseDecreaseThroughTreasuryShareTransactions",
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfCommonAndPreferredStock",
        "PaymentsForRepurchaseOfEquity",
        "PaymentsForRepurchaseOfSharesClassifiedAsEquity",
    ),
    "dividends": (
        "DividendsRecognisedAsDistributionsToOwnersOfParent",
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfDividends",
        "DividendsPaidClassifiedAsFinancingActivities",
        "DividendsPaid",
    ),
    "acquisitions": (
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesGross",
        "BusinessAcquisitionsNetOfCashAcquired",
        "CashFlowsUsedInLosingControlOfSubsidiariesOrOtherBusinessesClassifiedAsInvestingActivities",
        "PurchaseOfInvestmentsOtherThanInvestmentsAccountedForUsingEquityMethod",
    ),
    "debt_issuance": (
        "ProceedsFromIssueOfBondsNotesAndDebentures",
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfDebt",
        "ProceedsFromShortTermDebt",
        "ProceedsFromNoncurrentBorrowings",
        "ProceedsFromCurrentBorrowings",
        "ProceedsFromBorrowings",
    ),
    "debt_repayment": (
        "RepaymentsOfBondsNotesAndDebentures",
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
        "RepaymentsOfShortTermDebt",
        "RepaymentsOfNoncurrentBorrowings",
        "RepaymentsOfCurrentBorrowings",
        "RepaymentsOfBorrowings",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForProceedsFromOtherPropertyPlantAndEquipment",
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "PurchaseOfPropertyPlantAndEquipment",
    ),
    "r_and_d": (
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentExpense",
    ),
    "equity_compensation": (
        "AdjustmentsForSharebasedPayments",
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
        "ExpenseFromSharebasedPaymentTransactionsInWhichGoodsOrServicesReceivedDidNotQualifyForRecognitionAsAssets",
        "ShareBasedPaymentArrangementExpense",
    ),
}

SECTION_PATTERNS = (
    ("management_discussion_and_analysis", re.compile(
        r"\bmanagement(?:'s|’s)? discussion and analysis\b|\bmd&a\b",
        re.I,
    )),
    ("liquidity_and_capital_resources", re.compile(
        r"\bliquidity and capital resources\b",
        re.I,
    )),
    ("stockholders_equity", re.compile(r"\bstockholders?' equity\b", re.I)),
    ("debt_notes", re.compile(r"\b(?:long[- ]term )?debt\b", re.I)),
    ("cash_flow_statement", re.compile(r"\bstatements? of cash flows?\b", re.I)),
    ("business_combinations", re.compile(r"\bbusiness combinations?\b", re.I)),
    ("share_repurchase_programs", re.compile(
        r"\bshare repurchase programs?\b|\bissuer purchases of equity securities\b",
        re.I,
    )),
    ("earnings_per_share", re.compile(r"\bearnings per share\b", re.I)),
    ("executive_compensation", re.compile(r"\bexecutive compensation\b", re.I)),
    ("notes_to_financial_statements", re.compile(
        r"\bnotes? to (?:the )?(?:consolidated )?financial statements\b",
        re.I,
    )),
)

METRIC_TERMS = {
    "buybacks": re.compile(r"\brepurchas(?:e|ed|es|ing)\b|\bbuybacks?\b", re.I),
    "dividends": re.compile(r"\bdividends?\b", re.I),
    "acquisitions": re.compile(
        r"\bacquisitions?\b|\bbusiness combinations?\b",
        re.I,
    ),
    "debt_issuance": re.compile(
        r"\b(?:issued|issuance|proceeds from).{0,50}\b(?:debt|notes|borrowings)\b",
        re.I,
    ),
    "debt_repayment": re.compile(
        r"\b(?:repay|repaid|repayment|maturit).{0,50}\b(?:debt|notes|borrowings)\b",
        re.I,
    ),
    "capex": re.compile(
        r"\bcapital expenditures?\b|\bproperty, plant and equipment\b",
        re.I,
    ),
    "r_and_d": re.compile(
        r"\bresearch and development\b|\bR&D\b",
        re.I,
    ),
    "equity_compensation": re.compile(
        r"\bshare[- ]based compensation\b|\bstock[- ]based compensation\b",
        re.I,
    ),
    "share_dilution": re.compile(
        r"\bshares outstanding\b|\bdilutive securities\b|\bdiluted shares\b",
        re.I,
    ),
}


def _filing_url(cik: str, accession: str) -> str:
    return SEC_FILING_INDEX_URL.format(
        cik=int(cik),
        accession_path=accession.replace("-", ""),
        accession=accession,
    )


def _duration_days(fact: dict[str, Any]) -> int | None:
    try:
        return (
            date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])
        ).days
    except (KeyError, TypeError, ValueError):
        return None


def _empty_amount_metric() -> dict[str, Any]:
    return {
        "amount": None,
        "currency": None,
        "period_start": None,
        "period_end": None,
        "period_type": None,
        "status": "unavailable",
        "basis": None,
        "concept": None,
        "sources": [],
        "filing_evidence": [],
    }


def _empty_share_dilution() -> dict[str, Any]:
    return {
        "shares_change_percent": None,
        "beginning_shares": None,
        "ending_shares": None,
        "beginning_period_end": None,
        "ending_period_end": None,
        "status": "unavailable",
        "basis": None,
        "sources": [],
        "filing_evidence": [],
    }


def _fact_source(
    fact: dict[str, Any],
    *,
    cik: str,
    concept: str,
    section: str,
    unit: str,
) -> dict[str, Any]:
    accession = str(fact["accn"])
    return {
        "source_form": fact.get("form"),
        "source_accession": accession,
        "source_url": _filing_url(cik, accession),
        "filing_date": fact.get("filed"),
        "report_date": fact.get("end"),
        "section": section,
        "evidence": (
            f"SEC XBRL fact {concept} reported {fact.get('val')} {unit} "
            f"for {fact.get('start')} through {fact.get('end')}."
        ),
    }


def _facts_for_concept(
    us_gaap: dict[str, Any],
    concept: str,
) -> tuple[list[dict[str, Any]], str | None]:
    units = us_gaap.get(concept, {}).get("units", {})
    if not units:
        return [], None
    target_unit = "USD" if "USD" in units else list(units.keys())[0]
    return list(units[target_unit]), target_unit


def _select_duration_fact(
    us_gaap: dict[str, Any],
    concepts: tuple[str, ...],
    *,
    annual: bool,
) -> tuple[dict[str, Any], str, str] | None:
    allowed_forms = {"10-K", "20-F", "40-F"} if annual else {"10-Q", "6-K"}
    for concept in concepts:
        all_facts, unit = _facts_for_concept(us_gaap, concept)
        if not unit:
            continue
        candidates = [
            fact
            for fact in all_facts
            if fact.get("form") in allowed_forms
            and fact.get("start")
            and fact.get("end")
            and isinstance(fact.get("val"), (int, float))
        ]
        if annual:
            candidates = [
                fact
                for fact in candidates
                if fact.get("fp") == "FY"
                or (_duration_days(fact) or 0) >= 270
            ]
        if not candidates:
            continue
        selected = max(
            candidates,
            key=lambda fact: (
                fact.get("end", ""),
                fact.get("filed", ""),
            ),
        )
        return selected, concept, unit
    return None


def _amount_metric(
    us_gaap: dict[str, Any],
    metric: str,
    *,
    cik: str,
    annual_filing: dict[str, str] | None,
    quarterly_filing: dict[str, str] | None,
) -> dict[str, Any]:
    selection = None
    period_type = None
    if annual_filing and annual_filing.get("form") in {"10-K", "20-F", "40-F"}:
        selection = _select_duration_fact(
            us_gaap,
            CAPITAL_ALLOCATION_CONCEPTS[metric],
            annual=True,
        )
        period_type = "annual" if selection else None
    if (
        selection is None
        and quarterly_filing
        and quarterly_filing.get("form") == "10-Q"
    ):
        selection = _select_duration_fact(
            us_gaap,
            CAPITAL_ALLOCATION_CONCEPTS[metric],
            annual=False,
        )
        period_type = "interim" if selection else None
    if selection is None:
        return _empty_amount_metric()

    fact, concept, unit = selection
    amount = abs(float(fact["val"]))
    if isinstance(fact["val"], int):
        amount = int(amount)
    return {
        "amount": amount,
        "currency": unit,
        "period_start": fact.get("start"),
        "period_end": fact.get("end"),
        "period_type": period_type,
        "status": "reported",
        "basis": (
            "Direct SEC XBRL fact; cash outflow concepts are normalized to a "
            "positive allocation amount."
        ),
        "concept": concept,
        "sources": [
            _fact_source(
                fact,
                cik=cik,
                concept=concept,
                section="sec_xbrl_companyfacts",
                unit="USD",
            )
        ],
        "filing_evidence": [],
    }


def _annual_shares(
    dei: dict[str, Any],
    *,
    latest_annual_accession: str,
) -> list[dict[str, Any]]:
    facts = (
        dei.get("EntityCommonStockSharesOutstanding", {})
        .get("units", {})
        .get("shares", [])
    )
    by_end: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if (
            fact.get("form") not in {"10-K", "20-F", "40-F"}
            or fact.get("start")
            or not fact.get("end")
            or not fact.get("accn")
            or not isinstance(fact.get("val"), (int, float))
        ):
            continue
        existing = by_end.get(fact["end"])
        if existing is None or fact.get("filed", "") > existing.get("filed", ""):
            by_end[fact["end"]] = fact
    rows = sorted(
        by_end.values(),
        key=lambda fact: (fact["end"], fact.get("filed", "")),
    )
    latest_indexes = [
        index
        for index, fact in enumerate(rows)
        if fact.get("accn") == latest_annual_accession
    ]
    if not latest_indexes:
        return []
    latest_index = latest_indexes[-1]
    if latest_index == 0:
        return []
    return [rows[latest_index - 1], rows[latest_index]]


def _share_dilution_metric(
    dei: dict[str, Any],
    *,
    cik: str,
    annual_filing: dict[str, str] | None,
) -> dict[str, Any]:
    if not annual_filing or annual_filing.get("form") not in {"10-K", "20-F", "40-F"}:
        return _empty_share_dilution()
    rows = _annual_shares(
        dei,
        latest_annual_accession=annual_filing["accession"],
    )
    if len(rows) != 2:
        return _empty_share_dilution()
    beginning, ending = rows
    beginning_value = float(beginning["val"])
    ending_value = float(ending["val"])
    if beginning_value <= 0:
        return _empty_share_dilution()
    change = (ending_value - beginning_value) / beginning_value * 100
    return {
        "shares_change_percent": round(change, 4),
        "beginning_shares": beginning["val"],
        "ending_shares": ending["val"],
        "beginning_period_end": beginning["end"],
        "ending_period_end": ending["end"],
        "status": "derived",
        "basis": (
            "(ending reported common shares outstanding - beginning reported "
            "common shares outstanding) / beginning shares outstanding * 100"
        ),
        "sources": [
            _fact_source(
                fact,
                cik=cik,
                concept="EntityCommonStockSharesOutstanding",
                section="sec_xbrl_companyfacts",
                unit="shares",
            )
            for fact in rows
        ],
        "filing_evidence": [],
    }


def _section_name(text: str) -> str | None:
    if (
        len(text) > 180
        or len(text.split()) > 20
        or re.search(r"[.;!?]$", text)
    ):
        return None
    for section, pattern in SECTION_PATTERNS:
        if pattern.search(text):
            return section
    return None


def collect_capital_allocation_passages(
    filings: list[dict[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    passages = {metric: [] for metric in METRIC_TERMS}
    seen: set[tuple[str, str, str]] = set()
    for filing in filings:
        if filing.get("form") not in {"10-K", "20-F", "40-F", "10-Q"}:
            continue
        parser = _FilingTextParser()
        parser.feed(filing.get("html", ""))
        parser.close()
        section = None
        for block in parser.blocks:
            heading = _section_name(block)
            if heading:
                section = heading
                continue
            evidence = _normalize_text(block)
            if not 30 <= len(evidence) <= 1200:
                continue
            for metric, pattern in METRIC_TERMS.items():
                if not pattern.search(evidence):
                    continue
                key = (metric, filing.get("accession", ""), evidence)
                if key in seen or len(passages[metric]) >= 2:
                    continue
                seen.add(key)
                passages[metric].append(
                    {
                        "source_form": filing.get("form"),
                        "source_accession": filing.get("accession"),
                        "source_url": filing.get("source_url"),
                        "filing_date": filing.get("filing_date") or None,
                        "report_date": filing.get("report_date") or None,
                        "section": section or "unclassified",
                        "evidence": evidence,
                    }
                )
    return passages


def extract_capital_allocation(
    ticker: str,
    companyfacts: dict[str, Any],
    filings: list[dict[str, str]],
    *,
    cik: str,
) -> dict[str, Any]:
    annual_filing = next(
        (filing for filing in filings if filing.get("form") in {"10-K", "20-F", "40-F"}),
        None,
    )
    quarterly_filing = next(
        (filing for filing in filings if filing.get("form") == "10-Q"),
        None,
    )
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    ifrs_full = companyfacts.get("facts", {}).get("ifrs-full", {})
    gaap_facts = {**us_gaap, **ifrs_full}
    dei = companyfacts.get("facts", {}).get("dei", {})
    metrics = {
        metric: _amount_metric(
            gaap_facts,
            metric,
            cik=cik,
            annual_filing=annual_filing,
            quarterly_filing=quarterly_filing,
        )
        for metric in CAPITAL_ALLOCATION_CONCEPTS
    }
    metrics["share_dilution"] = _share_dilution_metric(
        dei,
        cik=cik,
        annual_filing=annual_filing,
    )
    filing_passages = collect_capital_allocation_passages(filings)
    for metric, passages in filing_passages.items():
        metrics[metric]["filing_evidence"] = passages

    fiscal_year = None
    if annual_filing and annual_filing.get("report_date"):
        try:
            fiscal_year = int(annual_filing["report_date"][:4])
        except ValueError:
            fiscal_year = None
    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "analyzed_filings": [
            {
                "form": filing.get("form"),
                "accession": filing.get("accession"),
                "filing_date": filing.get("filing_date") or None,
                "report_date": filing.get("report_date") or None,
                "source_url": filing.get("source_url"),
            }
            for filing in filings
            if filing.get("form") in {"10-K", "20-F", "40-F", "10-Q"}
        ],
        "capital_allocation": metrics,
    }
