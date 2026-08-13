import pytest

from app.services.valuation_engines import (
    calculate_asset_based_valuation,
    calculate_ddm_valuation,
    calculate_implied_expectations,
    calculate_capitalized_rnd,
    calculate_growth_multistage_dcf,
    calculate_rnd_capitalization,
    calculate_fcfe,
    calculate_normalized_median_dcf,
    calculate_relative_valuation,
    calculate_residual_income_valuation,
    calculate_standard_driver_dcf,
    run_monte_carlo_simulation,
)


def test_rnd_capitalization_uses_full_straight_line_research_asset_schedule():
    result = calculate_rnd_capitalization([40, 50, 60, 70, 80, 90], 5)

    assert result["amortization_of_rnd"] == pytest.approx(60)
    assert result["capitalized_rnd_asset"] == pytest.approx(230)
    assert result["rnd_amortization_period_years"] == 5
    assert result["rnd_history_years_used"] == 6


def test_growth_multistage_dcf_anchors_consensus_then_fades_to_terminal_economics():
    estimates = [
        {"date": "2026-12-31", "revenueLow": 1050, "revenueAvg": 1100, "revenueHigh": 1150,
         "ebitLow": 105, "ebitAvg": 132, "ebitHigh": 161},
        {"date": "2027-12-31", "revenueLow": 1120, "revenueAvg": 1210, "revenueHigh": 1300,
         "ebitLow": 112, "ebitAvg": 157.3, "ebitHigh": 195},
    ]
    result = calculate_growth_multistage_dcf(
        base_revenue=1000,
        operating_income=100,
        tax_rate=0.20,
        shares_outstanding=100,
        total_debt=100,
        cash_and_equivalents=50,
        current_wacc=0.12,
        terminal_wacc=0.09,
        stage_1_growth_rate=0.08,
        perpetual_growth_rate=0.03,
        sales_to_capital=2.0,
        projection_years=6,
        consensus_estimates=estimates,
        base_fiscal_year=2025,
        stable_ebit_margin=0.15,
        trailing_rnd=[40, 50, 60, 70, 80, 90],
        rnd_amortization_years=5,
    )

    first, second, final = result["revenue_projections"][0], result["revenue_projections"][1], result["revenue_projections"][-1]
    assert first["revenue"] == pytest.approx(1100)
    assert second["revenue"] == pytest.approx(1210)
    assert first["forecast_stage"] == "consensus"
    assert first["reported_consensus_ebit_margin"] == pytest.approx(0.12)
    assert first["rnd_ebit_margin_adjustment"] == pytest.approx(0.03)
    assert first["ebit_margin"] == pytest.approx(0.15)
    assert first["rnd_tax_benefit"] == pytest.approx(6)
    assert first["nopat"] == pytest.approx(first["ebit"] * 0.80 + 6)
    assert first["reinvestment"] == pytest.approx(50)
    assert final["wacc"] == pytest.approx(0.09)
    assert final["growth_rate"] == pytest.approx(0.03)
    assert result["terminal_roic"] == pytest.approx(0.09)
    assert result["terminal_reinvestment_rate"] == pytest.approx(1 / 3)
    assert result["terminal_nopat"] == pytest.approx(
        result["terminal_ebit"] * 0.80 + 6
    )
    assert result["sales_to_capital_ratio_capped"] is False
    assert result["share_normalization_basis"] == "equity_value_usd / current_point_in_time_shares"


def test_growth_multistage_dcf_rejects_flat_margin_consensus_that_diverges_from_base():
    # Reproduces a provider backfilling out-year EBIT as a flat percentage of
    # revenue rather than genuine per-year analyst judgment (observed live for
    # AMZN and TSLA): margin is bit-identical across every forecast year and
    # diverges sharply from the company's own current sourced operating
    # margin. Revenue consensus should still drive growth; margin should not.
    estimates = [
        {"date": "2026-12-31", "revenueLow": 1050, "revenueAvg": 1100, "revenueHigh": 1150,
         "ebitLow": 50, "ebitAvg": 55, "ebitHigh": 60},
        {"date": "2027-12-31", "revenueLow": 1160, "revenueAvg": 1210, "revenueHigh": 1260,
         "ebitLow": 55, "ebitAvg": 60.5, "ebitHigh": 66},
        {"date": "2028-12-31", "revenueLow": 1280, "revenueAvg": 1331, "revenueHigh": 1380,
         "ebitLow": 61, "ebitAvg": 66.55, "ebitHigh": 72},
    ]
    result = calculate_growth_multistage_dcf(
        base_revenue=1000,
        operating_income=150,  # 15% current sourced margin
        tax_rate=0.20,
        shares_outstanding=100,
        total_debt=100,
        cash_and_equivalents=50,
        current_wacc=0.12,
        terminal_wacc=0.09,
        stage_1_growth_rate=0.08,
        perpetual_growth_rate=0.03,
        sales_to_capital=2.0,
        projection_years=6,
        consensus_estimates=estimates,
        base_fiscal_year=2025,
        stable_ebit_margin=0.12,
        trailing_rnd=None,
    )

    assert result["margin_consensus_rejected"] is True
    assert "flat" in result["margin_consensus_rejection_reason"].lower()
    first = result["revenue_projections"][0]
    # Revenue growth still tracks the (separately trustworthy) consensus...
    assert first["revenue"] == pytest.approx(1100)
    # ...but margin falls back to the current sourced margin instead of the
    # rejected flat 5% consensus, both for the anchor years and the terminal
    # value — never a stale trailing multi-year median that could include a
    # crisis year no longer representative of the current run-rate.
    assert first["ebit_margin"] == pytest.approx(0.15)
    assert result["terminal_margin_basis"].startswith("current sourced operating margin")
    assert result["terminal_margin"] == pytest.approx(0.15)


def test_growth_multistage_dcf_terminal_margin_prefers_varying_consensus_over_historical_median():
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
        projection_years=6,
        consensus_estimates=estimates,
        base_fiscal_year=2025,
        stable_ebit_margin=0.06,  # a lower, stale historical median that must not win
        trailing_rnd=None,
    )

    assert result["margin_consensus_rejected"] is False
    assert result["terminal_margin_basis"] == (
        "final validated consensus year EBIT margin + capitalized R&D adjustment"
    )
    assert result["terminal_margin"] == pytest.approx(157.3 / 1210)


def test_growth_multistage_dcf_terminal_margin_falls_back_to_current_margin_not_stale_median():
    # With no consensus at all, terminal margin must anchor to the company's
    # current sourced operating margin rather than a multi-year historical
    # median (which can include a crisis/outlier year no longer representative
    # of the current run-rate, as observed live for AMZN's 2022 margin crash).
    result = calculate_growth_multistage_dcf(
        base_revenue=1000,
        operating_income=200,  # 20% current sourced margin
        tax_rate=0.20,
        shares_outstanding=100,
        total_debt=100,
        cash_and_equivalents=50,
        current_wacc=0.12,
        terminal_wacc=0.09,
        stage_1_growth_rate=0.08,
        perpetual_growth_rate=0.03,
        sales_to_capital=2.0,
        projection_years=6,
        consensus_estimates=None,
        base_fiscal_year=2025,
        stable_ebit_margin=0.03,  # a stale historical median that must not win
        trailing_rnd=None,
    )

    assert result["margin_consensus_rejected"] is False
    assert result["terminal_margin_basis"].startswith("current sourced operating margin")
    assert "unavailable" in result["terminal_margin_basis"]
    assert result["terminal_margin"] == pytest.approx(0.20)


def test_overview_engines_expose_backend_presentation_basis_without_fallbacks():
    asset = calculate_asset_based_valuation(1_000, 400, 50, 25, 10)
    assert asset["standard_nav_per_share"] == 60
    assert asset["tangible_net_net_per_share"] == 52.5
    assert asset["calculation_basis"]["default_fair_value"] == "tangible_net_net_per_share"

    ddm = calculate_ddm_valuation(0, 10, [1, 1.1], 0.10)
    assert ddm["status"] == "DDM_INAPPLICABLE"
    assert ddm["computed_fair_value"] is None
    assert "no sourced dividend" in ddm["calculation_basis"]

    residual = calculate_residual_income_valuation(1_000, 100, 100, 0.09)
    assert residual["book_value_per_share"] == 10
    assert residual["pv_future_wealth_per_share"] == pytest.approx(
        residual["pv_future_wealth"] / 100
    )
    assert residual["book_value_component_percentage"] + residual["future_wealth_component_percentage"] == pytest.approx(100)
    assert residual["composition_available"] is True


def test_ddm_formula_matches_gordon_growth_model():
    result = calculate_ddm_valuation(
        dividends_paid=200,
        shares_outstanding=100,
        historical_dividends=[160, 168, 176],
        cost_of_equity=0.10,
    )

    expected_growth = (176 / 160) ** (1 / 2) - 1
    expected_value = 2 * (1 + expected_growth) / (0.10 - expected_growth)
    assert result["dividend_growth_cagr"] == pytest.approx(expected_growth)
    assert result["computed_fair_value"] == pytest.approx(expected_value)


def test_relative_formula_uses_peer_medians_and_equity_bridge():
    result = calculate_relative_valuation(
        target_eps=4,
        target_bvps=20,
        target_ebitda=100,
        target_debt=40,
        target_cash=10,
        shares_outstanding=10,
        peers=[
            {"pe": 10, "pb": 1, "ev_ebitda": 5},
            {"pe": 20, "pb": 2, "ev_ebitda": 10},
            {"pe": 30, "pb": 3, "ev_ebitda": 15},
        ],
    )

    assert result["fv_pe"] == 80
    assert result["fv_pb"] == 40
    assert result["fv_ev_ebitda"] == 97
    assert result["computed_fair_value"] == pytest.approx((80 + 40 + 97) / 3)


def test_residual_income_formula_discounts_each_year_and_terminal_value():
    result = calculate_residual_income_valuation(
        bv_0=1_000,
        net_income=120,
        shares_outstanding=100,
        cost_of_equity=0.10,
        dividend_payout_ratio=0.25,
        persistence_factor=0.50,
    )

    roe = 0.12
    book_value = 1_000.0
    residual_incomes = []
    for _ in range(5):
        forecast_income = book_value * roe
        residual_incomes.append(forecast_income - book_value * 0.10)
        book_value += forecast_income * 0.75
    terminal_value = residual_incomes[-1] * 0.50 / (1.10 - 0.50)
    expected_future_wealth = sum(
        value / (1.10 ** year)
        for year, value in enumerate(residual_incomes, start=1)
    ) + terminal_value / (1.10 ** 5)

    assert result["residual_incomes"] == pytest.approx(residual_incomes)
    assert result["terminal_value"] == pytest.approx(terminal_value)
    assert result["computed_fair_value"] == pytest.approx(
        (1_000 + expected_future_wealth) / 100
    )


def test_residual_income_keeps_negative_future_wealth_as_a_signed_component():
    result = calculate_residual_income_valuation(
        bv_0=1_000,
        net_income=40,
        shares_outstanding=100,
        cost_of_equity=0.10,
        dividend_payout_ratio=0.0,
        persistence_factor=0.50,
    )

    assert result["pv_future_wealth"] < 0
    assert result["pv_future_wealth_per_share"] < 0
    assert result["total_equity_value"] > 0
    assert result["computed_fair_value"] == pytest.approx(
        result["book_value_per_share"] + result["pv_future_wealth_per_share"]
    )
    # This flag governs whether a non-negative composition chart is possible;
    # it does not invalidate a completed signed residual-income valuation.
    assert result["composition_available"] is False


def test_calculate_capitalized_rnd_adjusts_ebit_and_reinvestment():
    result = calculate_capitalized_rnd(
        base_revenue=1000,
        operating_income=120,
        tax_rate=0.20,
        capex=80,
        depreciation_amortization=30,
        change_in_nwc=10,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.09,
        stage_1_growth_rate=0.05,
        perpetual_growth_rate=0.03,
        projection_years=5,
        trailing_rnd=[60, 75, 90],
        historical_change_in_revenue=100,
        risk_free_rate=0.04,
    )

    assert result["methodology"] == "Capitalized R&D DCF"
    assert result["amortization_of_rnd"] == 75
    assert result["capitalized_rnd_asset"] == 85
    assert result["adjusted_ebit"] == 135
    assert result["adjusted_nopat"] == 108
    assert result["rnd_ebit_adjustment"] == 15
    assert result["rnd_nopat_adjustment"] == 12
    assert result["adjusted_reinvestment"] == 150
    assert result["computed_fair_value"] > 0


def test_calculate_capitalized_rnd_falls_back_when_rnd_history_missing():
    result = calculate_capitalized_rnd(
        base_revenue=1000,
        operating_income=120,
        tax_rate=0.20,
        capex=80,
        depreciation_amortization=30,
        change_in_nwc=10,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.09,
        stage_1_growth_rate=0.05,
        perpetual_growth_rate=0.03,
        projection_years=5,
        trailing_rnd=[],
        historical_change_in_revenue=100,
    )

    assert result["methodology"] == "Standard Driver-Based DCF"
    assert result["fallback_reason"] == "historical R&D data incomplete or not normalized"
    assert result["rnd_capitalization_applied"] is False


def test_calculate_capitalized_rnd_rejects_non_usd_or_nonconsecutive_history():
    common = dict(
        base_revenue=1000, operating_income=120, tax_rate=0.20, capex=80,
        depreciation_amortization=30, change_in_nwc=10, shares_outstanding=10,
        total_debt=100, cash_and_equivalents=50, wacc=0.09,
        stage_1_growth_rate=0.05, perpetual_growth_rate=0.03, projection_years=5,
    )
    result = calculate_capitalized_rnd(
        **common,
        trailing_rnd=[
            {"value": 60, "unit": "TWD", "end": "2022-12-31", "form": "20-F"},
            {"value": 75, "unit": "TWD", "end": "2023-12-31", "form": "20-F"},
            {"value": 90, "unit": "TWD", "end": "2024-12-31", "form": "20-F"},
        ],
    )
    assert result["methodology"] == "Standard Driver-Based DCF"
    assert result["rnd_history_validation_error"] == "R&D history is not normalized to USD"


def test_calculate_fcfe_uses_cost_of_equity_and_defaults_tier1_ratio():
    result = calculate_fcfe(
        net_income=120,
        total_assets=2000,
        shares_outstanding=20,
        cost_of_equity=0.10,
        tier1_capital_ratio=None,
        net_income_growth_rate=0.04,
        asset_growth_rate=0.03,
        perpetual_growth_rate=0.03,
        projection_years=5,
        risk_free_rate=0.04,
    )

    first_year = result["asset_projections"][0]
    assert result["methodology"] == "Regulatory FCFE"
    assert result["discount_rate_basis"] == "cost_of_equity_only"
    assert result["wacc_used"] is False
    assert result["tier1_capital_ratio"] == 0.10
    assert result["tier1_capital_ratio_defaulted"] is True
    assert first_year["required_capital"] == 6
    assert result["computed_fair_value"] > 0


def test_standard_driver_dcf_caps_sales_to_capital_and_terminal_growth():
    result = calculate_standard_driver_dcf(
        base_revenue=1000,
        ebit_margin=0.12,
        tax_rate=0.20,
        capex=10,
        depreciation_amortization=5,
        change_in_nwc=0,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.08,
        stage_1_growth_rate=0.05,
        perpetual_growth_rate=0.06,
        projection_years=5,
        historical_change_in_revenue=100,
        risk_free_rate=0.04,
    )

    assert result["sales_to_capital_ratio"] == 4.0
    assert result["sales_to_capital_ratio_capped"] is True
    assert result["terminal_growth_rate"] == 0.04
    assert result["terminal_growth_capped_to_risk_free_rate"] is True


def test_driver_dcf_floors_sales_to_capital_and_caps_reinvestment_to_nopat():
    result = calculate_standard_driver_dcf(
        base_revenue=1000,
        ebit_margin=0.05,
        tax_rate=0.20,
        capex=1000,
        depreciation_amortization=0,
        change_in_nwc=0,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.09,
        stage_1_growth_rate=0.20,
        perpetual_growth_rate=0.02,
        projection_years=5,
        historical_change_in_revenue=200,
    )

    first_year = result["revenue_projections"][0]
    assert result["sales_to_capital_ratio"] == 1.0
    assert result["sales_to_capital_ratio_capped"] is True
    assert first_year["raw_reinvestment"] > first_year["max_reinvestment"]
    assert first_year["reinvestment_cap_applied"] is True
    assert first_year["reinvestment"] == pytest.approx(first_year["nopat"] * 0.80)
    assert first_year["free_cash_flow"] == pytest.approx(first_year["nopat"] * 0.20)


def test_driver_dcf_caps_terminal_wacc_only_for_terminal_value():
    result = calculate_standard_driver_dcf(
        base_revenue=1000,
        ebit_margin=0.12,
        tax_rate=0.20,
        capex=80,
        depreciation_amortization=30,
        change_in_nwc=10,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.1441,
        stage_1_growth_rate=0.05,
        perpetual_growth_rate=0.025,
        projection_years=3,
        historical_change_in_revenue=100,
        risk_free_rate=0.04,
    )

    terminal_fcf = result["fcf_projections"][-1]
    expected_terminal_value = (terminal_fcf * 1.025) / (0.10 - 0.025)
    assert result["discount_rate"] == 0.1441
    assert result["terminal_discount_rate"] == 0.10
    assert result["terminal_discount_rate_capped"] is True
    assert result["terminal_value"] == pytest.approx(expected_terminal_value)


def test_driver_dcf_fades_low_ebit_margin_to_mature_industry_floor():
    result = calculate_standard_driver_dcf(
        base_revenue=1000,
        ebit_margin=0.02,
        tax_rate=0.20,
        capex=80,
        depreciation_amortization=30,
        change_in_nwc=10,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.09,
        stage_1_growth_rate=0.05,
        perpetual_growth_rate=0.02,
        projection_years=5,
        historical_change_in_revenue=100,
    )

    projections = result["revenue_projections"]
    assert projections[0]["ebit_margin"] > 0.02
    assert projections[0]["ebit_margin_floor_applied"] is True
    assert projections[4]["ebit_margin"] == pytest.approx(0.08)


def test_normalized_median_dcf_uses_median_operating_margin():
    result = calculate_normalized_median_dcf(
        base_revenue=1000,
        historical_operating_margins=[0.04, 0.20, 0.10, 0.08, 0.12],
        tax_rate=0.20,
        capex=80,
        depreciation_amortization=30,
        change_in_nwc=10,
        shares_outstanding=10,
        total_debt=100,
        cash_and_equivalents=50,
        wacc=0.09,
        stage_1_growth_rate=0.04,
        perpetual_growth_rate=0.03,
        projection_years=5,
        historical_change_in_revenue=100,
    )

    assert result["methodology"] == "Normalized Median DCF"
    assert result["normalized_margin"] == 0.10
    assert result["normalized_base_ebit"] == 100


def test_monte_carlo_wrapper_returns_probability_ranges_from_10000_runs():
    def engine_runner(revenue_growth: float, operating_margin: float | None):
        return {
            "computed_fair_value": 100 * (1 + revenue_growth) * (1 + operating_margin)
        }

    result = run_monte_carlo_simulation(
        engine_runner=engine_runner,
        base_revenue_growth=0.05,
        base_operating_margin=0.12,
        revenue_growth_volatility=0.04,
        operating_margin_volatility=0.02,
        live_market_price=100.0,
    )

    assert result["bear_p10"] < result["base_p50"] < result["bull_p90"]
    assert result["iteration_count"] == 10_000
    assert result["valid_sample_count"] == 10_000
    assert result["distribution"] == "normal"
    assert result["random_seed"] == 42
    assert len(result["histogram_bins"]) == 40
    assert sum(item["count"] for item in result["histogram_bins"]) == 10_000
    assert sum(item["probability"] for item in result["histogram_bins"]) == pytest.approx(1.0)
    assert 0 <= result["live_price_percentile"] <= 100


def test_monte_carlo_wrapper_rejects_non_10000_iteration_runs():
    def engine_runner(revenue_growth: float, operating_margin: float | None):
        return {"computed_fair_value": revenue_growth + (operating_margin or 0)}

    with pytest.raises(ValueError, match="exactly 10,000"):
        run_monte_carlo_simulation(
            engine_runner=engine_runner,
            base_revenue_growth=0.05,
            base_operating_margin=0.12,
            revenue_growth_volatility=0.04,
            operating_margin_volatility=0.02,
            iterations=9999,
        )


def test_implied_expectations_goal_seek_converges_to_market_price():
    def engine_runner(revenue_growth: float, operating_margin: float | None):
        return {"computed_fair_value": 1000 * (1 + revenue_growth) * operating_margin}

    result = calculate_implied_expectations(
        engine_runner=engine_runner,
        live_market_price=150.0,
        base_revenue_growth=0.05,
        base_operating_margin=0.12,
    )

    assert result["solver_status"] == "converged"
    assert result["implied_revenue_cagr"] is not None
    assert result["implied_operating_margin"] is not None
    assert result["model_fair_value"] == pytest.approx(150.0, abs=0.01)
    assert "feasible_curve" in result
    assert isinstance(result["feasible_curve"], list)
    assert len(result["feasible_curve"]) > 1
    for point in result["feasible_curve"]:
        assert point["model_value"] == pytest.approx(150.0, abs=1.5) # Allow 1% tolerance of 150



def test_implied_expectations_supports_extreme_hyper_growth():
    def engine_runner(revenue_growth: float, operating_margin: float | None):
        return {"computed_fair_value": 100.0 * (1 + revenue_growth)}

    result = calculate_implied_expectations(
        engine_runner=engine_runner,
        live_market_price=280.0,
        base_revenue_growth=0.20,
        base_operating_margin=None,
    )

    assert result["solver_status"] == "converged"
    assert result["implied_revenue_cagr"] == pytest.approx(1.80, abs=0.0001)
    assert result["revenue_growth_bounds"] == [-0.05, 5.0]


def test_implied_expectations_supports_extreme_operating_margin():
    def engine_runner(revenue_growth: float, operating_margin: float | None):
        return {"computed_fair_value": 1000.0 * float(operating_margin or 0.0)}

    result = calculate_implied_expectations(
        engine_runner=engine_runner,
        live_market_price=900.0,
        base_revenue_growth=0.05,
        base_operating_margin=0.20,
    )

    assert result["solver_status"] == "converged"
    assert result["implied_operating_margin"] == pytest.approx(0.90, abs=0.0001)
    assert result["operating_margin_bounds"] == [0.01, 0.95]


def test_implied_expectations_preserves_pessimistic_growth_bound():
    def engine_runner(revenue_growth: float, operating_margin: float | None):
        return {"computed_fair_value": 100.0 * (1 + revenue_growth)}

    result = calculate_implied_expectations(
        engine_runner=engine_runner,
        live_market_price=96.0,
        base_revenue_growth=0.05,
        base_operating_margin=None,
    )

    assert result["implied_revenue_cagr"] == pytest.approx(-0.04, abs=0.0001)
