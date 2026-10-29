from app.services.summary import _are_consecutive_quarters, _get_ttm, _instant_value


def test_instant_value_tolerates_explicit_null_fact() -> None:
    assert _instant_value({"shares": None}, "shares") is None


def test_are_consecutive_quarters():
    # Only Q1 from different years -> not consecutive
    non_consecutive_cy = ["CY2023Q1", "CY2024Q1", "CY2025Q1", "CY2026Q1"]
    is_consec, _ = _are_consecutive_quarters(non_consecutive_cy)
    assert is_consec is False

    # 4 consecutive calendar quarters -> consecutive
    consecutive_cy = ["CY2025Q2", "CY2025Q3", "CY2025Q4", "CY2026Q1"]
    is_consec, keys = _are_consecutive_quarters(consecutive_cy)
    assert is_consec is True
    assert keys == ["CY2025Q2", "CY2025Q3", "CY2025Q4", "CY2026Q1"]


def test_get_ttm_falls_back_to_annual_when_quarterly_not_consecutive():
    financials = {
        "quarterly": {
            "cash_flow": {
                "rows": [
                    {
                        "id": "dividends_paid",
                        "cells": {
                            "CY2023Q1": {"value": 10.0},
                            "CY2024Q1": {"value": 10.0},
                            "CY2025Q1": {"value": 10.0},
                            "CY2026Q1": {"value": 20.0},
                        },
                    }
                ]
            }
        },
        "annual": {
            "cash_flow": {
                "rows": [
                    {
                        "id": "dividends_paid",
                        "cells": {
                            "2025-12-31": {"value": 80.0},
                            "ttm": {"value": 90.0},
                        },
                    }
                ]
            }
        },
    }
    # Non-consecutive quarters must not be summed (10+10+10+20=50 is wrong); fallback to annual ttm (90.0)
    ttm_val = _get_ttm(financials, "cash_flow", "dividends_paid")
    assert ttm_val == 90.0


from tests.allure_helpers import valuator_test

@valuator_test(
    epic="Summary & Fundamentals",
    feature="Instant Value",
    story="Fact Value Extraction",
    priority="P0",
    severity="critical",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-SUM-001"
)
def test_instant_value_returns_fact_value() -> None:
    assert _instant_value({"shares": {"value": 123.0}}, "shares") == 123.0
