from app.providers.sec import (
    IFRS_ANNUAL_CONCEPTS,
    US_GAAP_ANNUAL_CONCEPTS,
    _adaptive_valuation_data,
    _annual_series,
    _latest_instant,
)


def _duration_fact(value, end, *, start=None, concept_form="10-K", filed="2026-01-31"):
    return {
        "val": value,
        "start": start or f"{end[:4]}-01-01",
        "end": end,
        "form": concept_form,
        "fp": "FY",
        "fy": int(end[:4]),
        "filed": filed,
        "accn": f"000-test-{end}",
    }


def _instant_fact(value, end, *, filed="2026-01-31"):
    return {
        "val": value,
        "end": end,
        "form": "10-K",
        "fp": "FY",
        "fy": int(end[:4]),
        "filed": filed,
        "accn": f"000-test-{end}",
    }


def test_adaptive_valuation_data_maps_required_fields_without_scaling():
    facts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {
                "USD": [
                    _duration_fact(1000, "2023-12-31"),
                    _duration_fact(1200, "2024-12-31"),
                    _duration_fact(1500, "2025-12-31"),
                ]
            }
        },
        "OperatingIncomeLoss": {
            "units": {
                "USD": [
                    _duration_fact(100, "2023-12-31"),
                    _duration_fact(180, "2024-12-31"),
                    _duration_fact(300, "2025-12-31"),
                ]
            }
        },
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost": {
            "units": {"USD": [_duration_fact(90, "2025-12-31")]}
        },
        "PaymentsToAcquireProductiveAssets": {
            "units": {"USD": [_duration_fact(250, "2025-12-31")]}
        },
        "NetIncomeLoss": {
            "units": {"USD": [_duration_fact(210, "2025-12-31")]}
        },
        "CashAndCashEquivalentsAtCarryingValue": {
            "units": {"USD": [_instant_fact(450, "2025-12-31")]}
        },
        "LongTermDebtCurrent": {
            "units": {"USD": [_instant_fact(25, "2025-12-31")]}
        },
        "LongTermDebtNoncurrent": {
            "units": {"USD": [_instant_fact(125, "2025-12-31")]}
        },
        "CommonEquityTier1CapitalRatio": {
            "units": {"pure": [_instant_fact(0.13, "2025-12-31")]}
        },
    }
    instants = {
        "cash": _latest_instant(
            facts,
            ["CashAndCashEquivalentsAtCarryingValue"],
        ),
        "debt_current": _latest_instant(facts, ["LongTermDebtCurrent"]),
        "debt_noncurrent": _latest_instant(facts, ["LongTermDebtNoncurrent"]),
        "total_debt": None,
    }

    adaptive = _adaptive_valuation_data(
        profile={"sic": "3711", "sic_description": "Motor Vehicles"},
        financial_facts=facts,
        annual_concepts=US_GAAP_ANNUAL_CONCEPTS,
        instants=instants,
    )

    assert adaptive["sic_code"] == "3711"
    assert adaptive["r_and_d_history"][-1]["value"] == 90
    assert adaptive["capex_history"][-1]["concept"] == "PaymentsToAcquireProductiveAssets"
    assert adaptive["net_income_history"][-1]["value"] == 210
    assert adaptive["cash_and_cash_equivalents"]["value"] == 450
    assert adaptive["total_debt"]["value"] == 150
    assert adaptive["regulatory_capital"]["tier1_capital_ratio"]["value"] == 0.13
    assert adaptive["operating_margin_history"][-1]["value"] == 0.2


def test_annual_series_rejects_quarterly_duration_facts_mislabeled_as_fy():
    facts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {
                "USD": [
                    _duration_fact(
                        120,
                        "2019-04-30",
                        start="2019-02-01",
                    ),
                    _duration_fact(
                        130,
                        "2019-07-31",
                        start="2019-05-01",
                    ),
                    _duration_fact(
                        500,
                        "2020-01-31",
                        start="2019-02-01",
                    ),
                    _duration_fact(
                        550,
                        "2021-01-31",
                        start="2020-02-01",
                    ),
                ]
            }
        }
    }

    rows = _annual_series(
        facts,
        US_GAAP_ANNUAL_CONCEPTS["revenue"],
        limit=10,
    )

    assert [row["value"] for row in rows] == [500, 550]
    assert all(row["start"][:4] != row["end"][:4] for row in rows)


def test_adaptive_valuation_data_falls_back_to_empty_arrays_and_nulls():
    adaptive = _adaptive_valuation_data(
        profile={},
        financial_facts={},
        annual_concepts=US_GAAP_ANNUAL_CONCEPTS,
        instants={},
    )

    assert adaptive["sic_code"] is None
    assert adaptive["r_and_d_history"] == []
    assert adaptive["operating_margin_history"] == []
    assert adaptive["total_debt"] is None
    assert adaptive["cash_and_cash_equivalents"] is None
    assert adaptive["regulatory_capital"]["tier1_capital_ratio"] is None


def test_ifrs_rnd_history_merges_concept_name_changes_in_one_series():
    facts = {
        "ResearchExpense": {"units": {"EUR": [
            _duration_fact(70, "2022-12-31", concept_form="20-F"),
        ]}},
        "ResearchAndDevelopmentExpense": {"units": {"EUR": [
            _duration_fact(80, "2023-12-31", concept_form="20-F"),
            _duration_fact(90, "2024-12-31", concept_form="20-F"),
        ]}},
    }
    adaptive = _adaptive_valuation_data(
        profile={}, financial_facts=facts,
        annual_concepts=IFRS_ANNUAL_CONCEPTS, instants={},
    )
    assert [row["value"] for row in adaptive["r_and_d_history"]] == [70, 80, 90]
    assert {row["concept"] for row in adaptive["r_and_d_history"]} == {
        "ResearchExpense", "ResearchAndDevelopmentExpense"
    }
