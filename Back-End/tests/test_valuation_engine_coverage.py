"""Coverage matrix: one representative ticker per valuation category.

Two things are pinned here:

1. Routing lands on the same engine whether or not the Finnhub industry label
   is available. Engine selection drives the fair value, so it must not hinge
   on a single third-party string that can disappear on an outage.
2. Each engine's response carries the fields that category requires and none
   that belong to a different engine, so a consumer can tell which model
   actually ran.

Fixtures are used throughout: no network, safe for CI. The companion live
check is `scripts/live_valuation_engine_coverage_smoke.py`.
"""

import pytest
from statistics import median

from app.api.routes import valuation
from app.api.routes.sector_router import ValuationMethodology, get_valuation_methodology
from app.models import ValuationResponse
from app.services.valuation_engines import (
    calculate_fcfe,
    calculate_growth_multistage_dcf,
    calculate_normalized_median_dcf,
    calculate_standard_driver_dcf,
)
from tests.valuation_engine_coverage_cases import (
    DATA_SHAPE_CASES,
    ENGINE_COVERAGE_CASES,
)


def _case(engine: str):
    return next(case for case in ENGINE_COVERAGE_CASES if case.engine == engine)


def test_every_reachable_engine_has_exactly_one_representative():
    covered = {case.engine for case in ENGINE_COVERAGE_CASES}
    # INFRASTRUCTURE ("Fixed Leverage FCFE") is deliberately excluded: no branch
    # in get_valuation_methodology returns it, so it is currently unreachable
    # and cannot be represented by a real ticker.
    reachable = {
        ValuationMethodology.TECH.value,
        ValuationMethodology.FINANCIAL.value,
        ValuationMethodology.CYCLICAL.value,
        ValuationMethodology.STANDARD.value,
    }
    assert covered == reachable
    assert len(ENGINE_COVERAGE_CASES) == len(covered), "one representative per engine"


@pytest.mark.parametrize("case", ENGINE_COVERAGE_CASES, ids=lambda c: c.ticker)
def test_representative_routes_to_its_engine_with_industry_label(case):
    routed = get_valuation_methodology(
        case.sic_code, finnhub_industry=case.finnhub_industry
    )
    assert routed.value == case.engine


@pytest.mark.parametrize("case", ENGINE_COVERAGE_CASES, ids=lambda c: c.ticker)
def test_representative_routes_to_its_engine_without_industry_label(case):
    """Finnhub outage must not change which engine values the company.

    Regression guard for SIC 367x (semiconductors): before the fix, TSM/NVDA
    reached the growth engine only because Finnhub said "Semiconductors", so
    losing that label silently moved them onto the standard driver engine.
    """
    routed = get_valuation_methodology(case.sic_code, finnhub_industry=None)
    assert routed.value == case.engine


def test_semiconductor_sic_routes_to_tech_without_any_industry_label():
    for sic in ("3674", "3672", "3670", "3679"):
        assert get_valuation_methodology(sic) == ValuationMethodology.TECH


def _assert_key_contract(case, assumptions):
    for key in case.required_assumption_keys:
        assert key in assumptions, f"{case.ticker} ({case.engine}) must expose {key}"
    for key in case.forbidden_assumption_keys:
        assert key not in assumptions, (
            f"{case.ticker} ({case.engine}) must not expose {key}; "
            "that field belongs to a different engine"
        )


def test_financial_engine_output_is_equity_side_only():
    case = _case("Regulatory FCFE")
    result = calculate_fcfe(
        net_income=50_000.0,
        total_assets=4_000_000.0,
        shares_outstanding=2_800.0,
        cost_of_equity=0.102,
        tier1_capital_ratio=0.10,
        net_income_growth_rate=0.05,
        perpetual_growth_rate=0.02,
        projection_years=15,
        risk_free_rate=0.047,
    )

    _assert_key_contract(case, result)
    # A bank is valued on equity cash flow, so there is no enterprise value to
    # bridge from and the discount rate must be cost of equity, never WACC.
    assert result["discount_rate_basis"] == "cost_of_equity_only"
    assert result["wacc_used"] is False
    assert result["equity_value"] == pytest.approx(
        result["present_value_fcfe"] + result["present_value_terminal_value"]
    )


def test_cyclical_engine_normalizes_to_median_margin_not_latest_year():
    case = _case("Normalized Median DCF")
    margins = [0.04, 0.19, 0.08, 0.02, 0.11]
    result = calculate_normalized_median_dcf(
        base_revenue=100_000.0,
        historical_operating_margins=margins,
        tax_rate=0.20,
        capex=8_000.0,
        depreciation_amortization=6_000.0,
        change_in_nwc=500.0,
        shares_outstanding=4_000.0,
        total_debt=20_000.0,
        cash_and_equivalents=5_000.0,
        wacc=0.09,
        stage_1_growth_rate=0.03,
        perpetual_growth_rate=0.02,
        projection_years=15,
        risk_free_rate=0.047,
    )

    _assert_key_contract(case, result)
    # The entire point of the cyclical engine: value off the through-cycle
    # median, not whatever the most recent (possibly peak or trough) year was.
    assert result["normalized_margin"] == pytest.approx(median(margins))
    assert result["normalized_margin"] != pytest.approx(margins[-1])
    assert result["normalized_base_ebit"] == pytest.approx(100_000.0 * median(margins))


def test_standard_engine_caps_reinvestment_so_cash_flow_cannot_go_negative():
    case = _case("Standard Driver-Based DCF")
    result = calculate_standard_driver_dcf(
        base_revenue=100_000.0,
        ebit_margin=0.25,
        tax_rate=0.20,
        capex=9_000.0,
        depreciation_amortization=5_000.0,
        change_in_nwc=1_000.0,
        shares_outstanding=4_000.0,
        total_debt=20_000.0,
        cash_and_equivalents=5_000.0,
        wacc=0.09,
        stage_1_growth_rate=0.06,
        perpetual_growth_rate=0.02,
        projection_years=15,
        risk_free_rate=0.047,
    )

    _assert_key_contract(case, result)
    assert 1.0 <= result["sales_to_capital_ratio"] <= 4.0
    for row in result["revenue_projections"]:
        # Unlike the growth model, this engine caps reinvestment at a share of
        # NOPAT, so a profitable company can never project negative free cash.
        assert row["reinvestment"] <= row["nopat"] * 0.8 + 1e-6
        if row["nopat"] > 0:
            assert row["free_cash_flow"] >= 0


def test_tech_engine_exposes_growth_model_contract():
    case = _case("Capitalized R&D DCF")
    estimates = [
        {"date": "2026-12-31", "revenueLow": 1050, "revenueAvg": 1100, "revenueHigh": 1150,
         "ebitLow": 105, "ebitAvg": 121, "ebitHigh": 137},
        {"date": "2027-12-31", "revenueLow": 1160, "revenueAvg": 1210, "revenueHigh": 1260,
         "ebitLow": 133, "ebitAvg": 157.3, "ebitHigh": 181},
    ]
    result = calculate_growth_multistage_dcf(
        base_revenue=1000,
        operating_income=110,
        tax_rate=0.20,
        shares_outstanding=100,
        total_debt=100,
        cash_and_equivalents=50,
        current_wacc=0.12,
        terminal_wacc=0.09,
        stage_1_growth_rate=0.08,
        perpetual_growth_rate=0.03,
        sales_to_capital=2.0,
        projection_years=15,
        consensus_estimates=estimates,
        base_fiscal_year=2025,
        trailing_rnd=[40, 50, 60, 70, 80, 90],
        rnd_amortization_years=5,
    )

    _assert_key_contract(case, result)
    assert result["model_version"] == "growth_multistage_fcff_v3"
    assert result["projection_years"] == 15
    assert result["rnd_capitalization_applied"] is True
    assert result["capitalized_rnd_asset"] > 0
    # Terminal economics must tie growth to reinvestment (VALUATOR_CLAC_DOCS §4.4).
    assert result["terminal_roic"] == pytest.approx(0.09)
    assert result["terminal_reinvestment_rate"] == pytest.approx(0.03 / 0.09)
    assert result["terminal_margin_basis"]


@pytest.mark.parametrize("case", DATA_SHAPE_CASES, ids=lambda c: c.shape)
def test_data_shape_cases_are_documented_with_expectations(case):
    """The cross-cutting shapes are asserted live; keep their intent pinned here."""
    assert case.ticker
    assert case.rationale
    assert case.expectations, f"{case.shape} must state what correct behaviour looks like"


def test_non_positive_equity_is_never_published_as_a_fair_value(monkeypatch):
    """Applies to every engine, so it is pinned at the coverage level."""
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "sic_code": "5331",
        "capex": 80.0,
        "base_revenue": 1000.0,
        "ebit_margin": 0.10,
        "effective_tax_rate": 0.20,
        "shares_outstanding": 10.0,
        "total_debt": 100_000.0,
        "cash": 50.0,
        "stage_1_growth_rate_default": 0.05,
        "depreciation_amortization": 30.0,
        "change_in_nwc": 10.0,
        "adaptive_valuation_data": {
            "sic_code": "5331",
            "revenue_history": [{"value": 900.0}, {"value": 1000.0}],
        },
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "market_cap": 1000.0, "risk_free_rate": 0.04, "market_risk_premium": 0.055,
    })

    payload = valuation.get_dcf("TEST", discount_rate=0.10, projection_years=3)
    validated = ValuationResponse.model_validate(payload)

    assert payload["valuation_status"] == "UNAVAILABLE"
    assert validated.computed_fair_value is None
