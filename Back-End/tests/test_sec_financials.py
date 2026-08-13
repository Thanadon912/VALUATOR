from app.providers.sec_financials import extract_financial_statements


def _fact(
    value,
    end,
    *,
    start="2025-01-01",
    form="10-K",
    fp="FY",
    fy=2025,
    filed="2026-01-30",
    frame=None,
):
    payload = {
        "val": value,
        "start": start,
        "end": end,
        "form": form,
        "fp": fp,
        "fy": fy,
        "filed": filed,
        "accn": f"000-test-{end}",
    }
    if frame:
        payload["frame"] = frame
    return payload


from tests.allure_helpers import valuator_test

@valuator_test(
    epic="Financial Data Pipeline",
    feature="SEC Financials",
    story="Reported vs Derived Traceability",
    priority="P0",
    severity="blocker",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-SEC-001"
)
def test_extract_financials_keeps_reported_and_derived_cells_traceable():
    payload = {
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            _fact(1000, "2025-12-31"),
                            _fact(
                                210,
                                "2025-03-31",
                                start="2025-01-01",
                                form="10-Q",
                                fp="Q1",
                                frame="CY2025Q1",
                            ),
                            _fact(
                                220,
                                "2025-06-30",
                                start="2025-04-01",
                                form="10-Q",
                                fp="Q2",
                                frame="CY2025Q2",
                            ),
                            _fact(
                                230,
                                "2025-09-30",
                                start="2025-07-01",
                                form="10-Q",
                                fp="Q3",
                                frame="CY2025Q3",
                            ),
                            _fact(
                                240,
                                "2025-12-31",
                                start="2025-10-01",
                                form="10-K",
                                fp="FY",
                                frame="CY2025Q4",
                            ),
                        ],
                    },
                },
                "OperatingExpenses": {
                    "units": {"USD": [_fact(200, "2025-12-31")]},
                },
                "ResearchAndDevelopmentExpense": {
                    "units": {"USD": [_fact(50, "2025-12-31")]},
                },
                "InterestExpense": {
                    "units": {"USD": [_fact(10, "2025-12-31")]},
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [_fact(500, "2025-12-31")]},
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [_fact(120, "2025-12-31")]},
                },
                "LongTermDebtCurrent": {
                    "units": {
                        "USD": [
                            _fact(
                                20,
                                "2025-12-31",
                                start=None,
                            ),
                        ],
                    },
                },
                "LongTermDebtNoncurrent": {
                    "units": {
                        "USD": [
                            _fact(
                                80,
                                "2025-12-31",
                                start=None,
                            ),
                        ],
                    },
                },
            },
            "dei": {},
        },
    }

    statements = extract_financial_statements(payload)
    income = statements["annual"]["income"]
    cash_flow = statements["annual"]["cash_flow"]
    balance = statements["annual"]["balance_sheet"]

    assert income["periods"][0]["key"] == "ttm"
    revenue = next(row for row in income["rows"] if row["id"] == "total_revenue")
    assert revenue["cells"]["ttm"]["value"] == 900
    assert revenue["cells"]["ttm"]["status"] == "derived"
    assert revenue["cells"]["2025-12-31"]["status"] == "reported"

    fcf = next(row for row in cash_flow["rows"] if row["id"] == "free_cash_flow")
    assert fcf["cells"]["2025-12-31"]["value"] == 380
    assert fcf["cells"]["2025-12-31"]["basis"] == (
        "operating cash flow - capital expenditure"
    )

    debt = next(row for row in balance["rows"] if row["id"] == "total_debt")
    assert debt["cells"]["2025-12-31"]["value"] == 100
    assert debt["cells"]["2025-12-31"]["status"] == "derived"


def test_extract_financials_aggregates_debt_components_without_double_counting():
    payload = {
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [_fact(1000, "2025-12-31")]},
                },
                "CommercialPaper": {
                    "units": {"USD": [_fact(10, "2025-12-31", start=None)]},
                },
                "LongTermDebtCurrent": {
                    "units": {"USD": [_fact(20, "2025-12-31", start=None)]},
                },
                "LongTermDebtNoncurrent": {
                    "units": {"USD": [_fact(80, "2025-12-31", start=None)]},
                },
            },
            "dei": {},
        },
    }

    balance = extract_financial_statements(payload)["annual"]["balance_sheet"]
    rows = {row["id"]: row for row in balance["rows"]}

    current_debt = rows["short_term_debt"]["cells"]["2025-12-31"]
    total_debt = rows["total_debt"]["cells"]["2025-12-31"]

    assert current_debt["value"] == 30
    assert current_debt["status"] == "derived"
    assert set(current_debt["input_refs"]) == {"CommercialPaper", "LongTermDebtCurrent"}
    assert total_debt["value"] == 110
    assert total_debt["status"] == "derived"
    assert set(total_debt["input_refs"]) == {
        "CommercialPaper",
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
    }
    assert total_debt["source_facts"]


def test_extract_financials_keeps_marketable_securities_separate_from_cash():
    payload = {
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [_fact(1000, "2025-12-31")]},
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_fact(25, "2025-12-31", start=None)]},
                },
                "ShortTermInvestments": {
                    "units": {"USD": [_fact(40, "2025-12-31", start=None)]},
                },
                "MarketableSecuritiesNoncurrent": {
                    "units": {"USD": [_fact(60, "2025-12-31", start=None)]},
                },
            },
            "dei": {},
        },
    }

    balance = extract_financial_statements(payload)["annual"]["balance_sheet"]
    rows = {row["id"]: row for row in balance["rows"]}

    cash = rows["cash"]["cells"]["2025-12-31"]
    marketable = rows["marketable_securities"]["cells"]["2025-12-31"]

    assert cash["value"] == 25
    assert marketable["value"] == 100
    assert marketable["status"] == "derived"
    assert set(marketable["input_refs"]) == {
        "ShortTermInvestments",
        "MarketableSecuritiesNoncurrent",
    }


def test_extract_financials_leaves_missing_cells_unavailable():
    payload = {
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [_fact(1000, "2025-12-31")]},
                },
                "ResearchAndDevelopmentExpense": {
                    "units": {"USD": [_fact(600, "2025-12-31")]},
                },
                "OperatingExpenses": {
                    "units": {"USD": [_fact(200, "2025-12-31")]},
                },
            },
            "dei": {},
        },
    }

    income = extract_financial_statements(payload)["annual"]["income"]
    gross_profit = next(row for row in income["rows"] if row["id"] == "gross_profit")

    assert gross_profit["cells"]["2025-12-31"]["value"] is None
    assert gross_profit["cells"]["2025-12-31"]["status"] == "unavailable"


def _revenue_payload(facts):
    return {
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": facts},
                },
                "CostOfGoodsAndServicesSold": {
                    "units": {"USD": [
                        {**f, "val": f.get("val", 0) * 0.6} for f in facts
                    ]},
                },
                "OperatingExpenses": {
                    "units": {"USD": [
                        {**f, "val": f.get("val", 0) * 0.2} for f in facts
                    ]},
                },
            },
            "dei": {},
        },
    }


def test_ttm_prefers_annual_plus_q1_ytd_minus_prior_q1_ytd():
    payload = _revenue_payload(
        [
            _fact(1000, "2025-12-31", start="2025-01-01", fp="FY", fy=2025),
            _fact(
                260,
                "2026-03-31",
                start="2026-01-01",
                form="10-Q",
                fp="Q1",
                fy=2026,
                filed="2026-05-01",
            ),
            _fact(
                220,
                "2025-03-31",
                start="2025-01-01",
                form="10-Q",
                fp="Q1",
                fy=2025,
                filed="2025-05-01",
            ),
        ]
    )

    income = extract_financial_statements(payload)["annual"]["income"]
    revenue = next(row for row in income["rows"] if row["id"] == "total_revenue")
    ttm = revenue["cells"]["ttm"]

    assert ttm["value"] == 1040
    assert ttm["calculation_method"] == "annual_plus_current_ytd_minus_prior_ytd"
    assert ttm["period_start"] == "2025-04-01"
    assert ttm["period_end"] == "2026-03-31"
    assert [fact["role"] for fact in ttm["source_facts"]] == [
        "annual_base",
        "current_ytd",
        "prior_comparable_ytd",
    ]


def test_ttm_supports_six_month_ytd_for_non_calendar_fiscal_year():
    payload = _revenue_payload(
        [
            _fact(1200, "2025-06-30", start="2024-07-01", fp="FY", fy=2025),
            _fact(
                640,
                "2025-12-31",
                start="2025-07-01",
                form="10-Q",
                fp="Q2",
                fy=2026,
                filed="2026-02-05",
            ),
            _fact(
                560,
                "2024-12-31",
                start="2024-07-01",
                form="10-Q",
                fp="Q2",
                fy=2025,
                filed="2025-02-05",
            ),
        ]
    )

    income = extract_financial_statements(payload)["annual"]["income"]
    revenue = next(row for row in income["rows"] if row["id"] == "total_revenue")
    ttm = revenue["cells"]["ttm"]

    assert ttm["value"] == 1280
    assert ttm["period_start"] == "2025-01-01"
    assert ttm["period_end"] == "2025-12-31"
    assert ttm["calculation_method"] == "annual_plus_current_ytd_minus_prior_ytd"


def test_ttm_supports_nine_month_ytd_and_selects_latest_amendment():
    payload = _revenue_payload(
        [
            _fact(900, "2025-12-31", start="2025-01-01", fp="FY", fy=2025),
            _fact(
                780,
                "2026-09-30",
                start="2026-01-01",
                form="10-Q",
                fp="Q3",
                fy=2026,
                filed="2026-11-01",
            ),
            _fact(
                600,
                "2025-09-30",
                start="2025-01-01",
                form="10-Q",
                fp="Q3",
                fy=2025,
                filed="2025-11-01",
            ),
            _fact(
                610,
                "2025-09-30",
                start="2025-01-01",
                form="10-Q",
                fp="Q3",
                fy=2025,
                filed="2025-11-15",
            ),
        ]
    )

    income = extract_financial_statements(payload)["annual"]["income"]
    revenue = next(row for row in income["rows"] if row["id"] == "total_revenue")
    ttm = revenue["cells"]["ttm"]

    assert ttm["value"] == 1070
    assert ttm["source_facts"][2]["value"] == 610


def test_ttm_unavailable_when_prior_comparable_ytd_is_missing():
    payload = _revenue_payload(
        [
            _fact(1000, "2025-12-31", start="2025-01-01", fp="FY", fy=2025),
            _fact(
                260,
                "2026-03-31",
                start="2026-01-01",
                form="10-Q",
                fp="Q1",
                fy=2026,
                filed="2026-05-01",
            ),
        ]
    )

    income = extract_financial_statements(payload)["annual"]["income"]
    revenue = next(row for row in income["rows"] if row["id"] == "total_revenue")

    assert "ttm" not in revenue["cells"]
    assert "TTM" not in [period["label"] for period in income["periods"]]
