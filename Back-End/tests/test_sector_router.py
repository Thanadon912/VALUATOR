import pytest

from app.api.routes import valuation
from app.api.routes.sector_router import (
    ValuationMethodology,
    get_valuation_methodology,
)
from app.models import ValuationMethodologyResponse, ValuationResponse


def test_sector_router_routes_smoke_targets():
    assert get_valuation_methodology("3711") == ValuationMethodology.TECH
    assert get_valuation_methodology("6021") == ValuationMethodology.FINANCIAL
    assert get_valuation_methodology("2911") == ValuationMethodology.CYCLICAL
    assert get_valuation_methodology("5331") == ValuationMethodology.STANDARD


def test_sector_router_routes_retail_catalog_ecommerce_to_tech():
    # AMZN's SEC SIC code (5961, Retail-Catalog & Mail-Order Houses) must
    # reach the consensus-anchored growth engine like other frontier-tech
    # names, mirroring the "retail-catalog"/"e-commerce" terms already
    # recognized by sotp_configs.resolve_sotp_profile.
    assert get_valuation_methodology("5961") == ValuationMethodology.TECH


def test_sector_router_routes_branded_personal_care_to_standard_not_cyclical():
    # PG's SEC SIC code (2840, Soap/Detergent/Cleaning/Perfumes/Cosmetics) is
    # branded consumer staples, not a commodity chemicals producer, and must
    # not be smoothed through the cyclical normalized-median engine.
    assert get_valuation_methodology("2840") == ValuationMethodology.STANDARD
    for boundary in ("2841", "2842", "2843", "2844"):
        assert get_valuation_methodology(boundary) == ValuationMethodology.STANDARD


def test_sector_router_still_routes_commodity_chemicals_to_cyclical():
    # The rest of SIC division 28 (industrial/inorganic/organic chemicals,
    # plastics, agricultural chemicals) does track commodity input costs and
    # must remain on the cyclical engine after excluding 2840-2844.
    for sic in ("2810", "2821", "2839", "2845", "2870", "2899"):
        assert get_valuation_methodology(sic) == ValuationMethodology.CYCLICAL


def test_valuation_methodology_has_no_unimplemented_infrastructure_route():
    # A prior INFRASTRUCTURE = "Fixed Leverage FCFE" enum member had no
    # calculation function, no routing rule, and no call site anywhere in the
    # codebase. AGENTS.md's adaptive DCF spec lists exactly four routes.
    assert not hasattr(ValuationMethodology, "INFRASTRUCTURE")
    assert {m.value for m in ValuationMethodology} == {
        "Standard Driver-Based DCF",
        "Capitalized R&D DCF",
        "Regulatory FCFE",
        "Normalized Median DCF",
    }


def test_sector_router_defaults_to_standard_for_missing_or_corrupt_sic():
    assert get_valuation_methodology(None) == ValuationMethodology.STANDARD
    assert get_valuation_methodology("") == ValuationMethodology.STANDARD
    assert get_valuation_methodology("not-a-sic") == ValuationMethodology.STANDARD
    assert get_valuation_methodology("9999") == ValuationMethodology.STANDARD


def test_methodology_endpoint_exposes_placeholder_contract(monkeypatch):
    def fake_inputs(ticker: str):
        return {
            "sic_code": "3711",
            "sic_description": "Motor Vehicles & Passenger Car Bodies",
            "valuation_methodology": ValuationMethodology.TECH.value,
            "adaptive_valuation_data": {
                "sic_code": "3711",
                "sic_description": "Motor Vehicles & Passenger Car Bodies",
                "r_and_d_history": [],
                "net_income_history": [],
                "regulatory_capital": {
                    "tier1_capital_ratio": None,
                    "tier1_capital": None,
                },
                "capex_history": [],
                "total_debt": None,
                "cash_and_cash_equivalents": None,
                "operating_income_history": [],
                "operating_margin_history": [],
            },
    }

    monkeypatch.setattr(valuation, "get_valuation_inputs", fake_inputs)

    payload = valuation.get_methodology("TSLA")
    validated = ValuationMethodologyResponse.model_validate(payload)

    assert validated.ticker == "TSLA"
    assert validated.methodology == ValuationMethodology.TECH.value
    assert validated.sic_code == "3711"
    assert validated.adaptive_valuation_data.r_and_d_history == []


from tests.allure_helpers import valuator_test


def assert_sensitivity_center_matches_overview(payload):
    matrix = payload["forward_dcf"]["sensitivity_matrix"]
    center_row = matrix[len(matrix) // 2]
    center = center_row["cells"][len(center_row["cells"]) // 2]["fair_value"]
    assert center == pytest.approx(payload["computed_fair_value"])
    assert payload["forward_dcf"]["sensitivity_basis"]["scenario"] == "base"
    assert payload["forward_dcf"]["sensitivity_basis"]["center_fair_value"] == pytest.approx(
        payload["computed_fair_value"]
    )


def test_all_valuation_engines_publish_the_common_openapi_contract():
    from app.main import app

    schema = app.openapi()
    expected_response = {"$ref": "#/components/schemas/ValuationResponse"}
    for endpoint in (
        "asset-based",
        "dcf",
        "ddm",
        "relative",
        "residual-income",
    ):
        response_schema = schema["paths"][f"/api/v1/valuation/{endpoint}"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        assert response_schema == expected_response

    monte_carlo_fields = schema["components"]["schemas"]["MonteCarloResults"][
        "properties"
    ]
    assert {
        "bear_p10",
        "base_p50",
        "bull_p90",
        "iteration_count",
        "valid_sample_count",
        "distribution",
        "random_seed",
        "histogram_bins",
        "live_price_percentile",
    } <= monte_carlo_fields.keys()


def test_all_valuation_engines_return_valid_missing_input_contracts(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {})
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {})

    for handler in (
        valuation.get_asset_based,
        valuation.get_dcf,
        valuation.get_ddm,
        valuation.get_relative,
        valuation.get_residual_income,
    ):
        payload = handler("MISSING")
        validated = ValuationResponse.model_validate(payload)
        assert validated.ticker == "MISSING"
        assert validated.valuation_status == "MISSING_INPUT"

@valuator_test(
    epic="DCF",
    feature="Sector Routing",
    story="Financial FCFE Engine",
    priority="P0",
    severity="critical",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-DCF-001"
)
def test_dcf_endpoint_dispatches_financial_sic_to_fcfe(monkeypatch):
    def fake_inputs(ticker: str):
        return {
            "sic_code": "6021",
            "valuation_methodology": ValuationMethodology.FINANCIAL.value,
            "net_income": 120.0,
            "total_assets": 2000.0,
            "shares_outstanding": 20.0,
            "stage_1_growth_rate_default": 0.04,
            "regulatory_capital": {"tier1_capital_ratio": None},
            "adaptive_valuation_data": {
                "sic_code": "6021",
                "regulatory_capital": {"tier1_capital_ratio": None},
            },
        }

    monkeypatch.setattr(valuation, "get_valuation_inputs", fake_inputs)
    monkeypatch.setattr(
        valuation,
        "get_valuation_telemetry",
        lambda ticker: {
            "cost_of_equity": 0.10,
            "risk_free_rate": 0.04,
            "market_risk_premium": 0.055,
        },
    )

    payload = valuation.get_dcf("JPM", projection_years=3)
    validated = ValuationResponse.model_validate(payload)

    assert payload["valuation_status"] == "CALCULATED"
    assert validated.valuation_methodology == "Regulatory FCFE"
    assert validated.engine_metadata["tier_1_capital_ratio_used"] == 0.10
    assert validated.engine_metadata["projected_loan_growth"] == 0.04
    assert validated.engine_metadata["discount_rate_type"] == "Cost of Equity (Ke)"
    assert validated.projections[0].capital_deduction_label == "Required Regulatory Capital"
    assert validated.projections[0].capital_deduction_value == 8
    assert validated.projections[0].free_cash_flow_to_equity == pytest.approx(116.8)
    assumptions = payload["underlying_assumptions"]
    assert assumptions["methodology"] == ValuationMethodology.FINANCIAL.value
    assert assumptions["discount_rate_basis"] == "cost_of_equity_only"
    assert assumptions["wacc_used"] is False
    assert_sensitivity_center_matches_overview(payload)

    override_payload = valuation.get_dcf(
        "JPM",
        discount_rate=0.12,
        projection_years=3,
    )
    assert override_payload["valuation_status"] == "CALCULATED"
    assert override_payload["underlying_assumptions"]["discount_rate"] == 0.12
    assert override_payload["computed_fair_value"] < payload["computed_fair_value"]
    assert_sensitivity_center_matches_overview(override_payload)


@valuator_test(
    epic="DCF",
    feature="Sector Routing",
    story="Tech Engine Metadata",
    priority="P1",
    severity="normal",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-DCF-002"
)
def test_dcf_endpoint_exposes_tech_engine_metadata(monkeypatch):
    def fake_inputs(ticker: str):
        return {
            "sic_code": "3711",
            "valuation_methodology": ValuationMethodology.TECH.value,
            "capex": 80.0,
            "base_revenue": 1000.0,
            "ebit_margin": 0.12,
            "effective_tax_rate": 0.20,
            "shares_outstanding": 10.0,
            "total_debt": 100.0,
                "cash": 50.0,
                "bv_0": 500.0,
            "stage_1_growth_rate_default": 0.05,
            "operating_income": 120.0,
            "depreciation_amortization": 30.0,
            "change_in_nwc": 10.0,
                "r_and_d_history": [
                    {"value": 60.0, "unit": "USD", "end": "2022-12-31", "form": "10-K"},
                    {"value": 75.0, "unit": "USD", "end": "2023-12-31", "form": "10-K"},
                    {"value": 90.0, "unit": "USD", "end": "2024-12-31", "form": "10-K"},
                ],
            "adaptive_valuation_data": {
                "sic_code": "3711",
                "revenue_history": [
                    {"value": 900.0},
                    {"value": 1000.0},
                ],
            },
        }

    monkeypatch.setattr(valuation, "get_valuation_inputs", fake_inputs)
    monkeypatch.setattr(
        valuation,
        "get_valuation_telemetry",
        lambda ticker: {"risk_free_rate": 0.04, "market_risk_premium": 0.055},
    )

    payload = valuation.get_dcf("TSLA", wacc=0.09, projection_years=3)
    validated = ValuationResponse.model_validate(payload)

    assert validated.valuation_methodology == "Capitalized R&D DCF"
    assert validated.engine_metadata["capitalized_rnd_adjustment"] == 22.5
    assert validated.engine_metadata["capitalized_rnd_asset"] == 127.5
    assert validated.engine_metadata["rnd_nopat_adjustment"] == 22.5
    assert validated.engine_metadata["adjusted_ebit_margin"] == 0.1425
    assert validated.engine_metadata["assumed_amortization_years"] == 2
    assert validated.projections[0].revenue_growth == 0.05
    assert validated.projections[0].capital_deduction_label == "Reinvestment"
    assert validated.projections[0].unlevered_free_cash_flow is not None
    assert_sensitivity_center_matches_overview(payload)


def test_dcf_warns_when_last_consensus_year_materially_drives_fair_value(monkeypatch):
    estimates = [
        {
            "date": f"{year}-06-30",
            "revenueLow": revenue * 0.95,
            "revenueAvg": revenue,
            "revenueHigh": revenue * 1.05,
            "ebitLow": revenue * 0.43,
            "ebitAvg": revenue * 0.45432,
            "ebitHigh": revenue * 0.48,
            "numAnalystsRevenue": 16 if year == 2031 else 20,
        }
        for year, revenue in (
            (2027, 369_900_000_000),
            (2028, 426_000_000_000),
            (2029, 526_000_000_000),
            (2030, 655_800_000_000),
            (2031, 869_900_000_000),
        )
    ]

    monkeypatch.setattr(
        valuation,
        "get_valuation_inputs",
        lambda ticker: {
            "sic_code": "7372",
            "valuation_methodology": ValuationMethodology.TECH.value,
            "capex": 64_500_000_000,
            "base_revenue": 331_839_000_000,
            "ebit_margin": 0.467808,
            "effective_tax_rate": 0.189556,
            "shares_outstanding": 7_425_545_491,
            "total_debt": 128_808_300_000,
            "cash": 76_843_000_000,
            "bv_0": 442_300_000_000,
            "stage_1_growth_rate_default": 0.115,
            "operating_income": 155_237_000_000,
            "r_and_d_history": [
                {"value": value, "unit": "USD", "end": f"{year}-06-30", "form": "10-K"}
                for year, value in (
                    (2021, 20_716_000_000),
                    (2022, 24_512_000_000),
                    (2023, 27_195_000_000),
                    (2024, 29_510_000_000),
                    (2025, 32_488_000_000),
                    (2026, 35_562_000_000),
                )
            ],
            "analyst_estimates": estimates,
            "base_fiscal_year": 2026,
            "adaptive_valuation_data": {
                "sic_code": "7372",
                "revenue_history": [{"value": 281_724_000_000}, {"value": 331_839_000_000}],
            },
        },
    )
    monkeypatch.setattr(
        valuation,
        "get_valuation_telemetry",
        lambda ticker: {
            "risk_free_rate": 0.0402,
            "market_risk_premium": 0.055,
        },
    )

    payload = valuation.get_dcf("MSFT", wacc=0.102622, projection_years=15)
    sensitivity = payload["engine_metadata"]["consensus_horizon_sensitivity"]

    assert payload["valuation_status"] == "CALCULATED"
    assert sensitivity["removed_consensus_year"] == 2031
    assert sensitivity["full_consensus_years"] == [2027, 2028, 2029, 2030, 2031]
    assert sensitivity["warning_triggered"] is True
    assert sensitivity["assessment"] == "MATERIAL_DEPENDENCY"
    assert sensitivity["diagnostic_only"] is True
    assert sensitivity["primary_value_basis"] == "full_valid_consensus"
    assert sensitivity["source_refs"] == ["fmp:analyst-estimates"]
    assert sensitivity["last_consensus_revenue_growth_basis"] == (
        "last revenueAvg / prior revenueAvg - 1"
    )
    assert sensitivity["last_consensus_revenue_growth_percentage"] == pytest.approx(
        32.65, abs=0.01
    )
    assert sensitivity["last_consensus_revenue_analyst_count"] == 16
    assert sensitivity["relative_delta_percentage"] >= 20
    assert sensitivity["full_fair_value"] == pytest.approx(payload["computed_fair_value"])
    matrix = payload["forward_dcf"]["sensitivity_matrix"]
    matrix_center = matrix[2]["cells"][2]["fair_value"]
    assert matrix_center == pytest.approx(payload["computed_fair_value"])
    assert payload["forward_dcf"]["sensitivity_basis"] == {
        "scenario": "base",
        "center_growth_rate": payload["underlying_assumptions"]["stage_1_growth_rate"],
        "center_discount_rate": payload["underlying_assumptions"]["wacc"],
        "discount_rate_driver": "current_wacc",
        "center_fair_value": pytest.approx(payload["computed_fair_value"]),
        "overview_fair_value": pytest.approx(payload["computed_fair_value"]),
        "calculation_basis": "active base-case inputs with only the matrix growth and discount-rate coordinates varied",
    }
    for row in matrix:
        row_values = [cell["fair_value"] for cell in row["cells"]]
        assert row_values == sorted(row_values, reverse=True)
    for column_index in range(5):
        column_values = [row["cells"][column_index]["fair_value"] for row in matrix]
        assert column_values == sorted(column_values)
    assert any(
        "LAST_CONSENSUS_YEAR_MATERIAL_DEPENDENCY" in warning
        for warning in payload["underlying_assumptions"]["computational_warnings"]
    )

    estimates[-1].pop("numAnalystsRevenue")
    missing_coverage_payload = valuation.get_dcf(
        "MSFT", wacc=0.102622, projection_years=15
    )
    assert (
        missing_coverage_payload["engine_metadata"]["consensus_horizon_sensitivity"]
        ["last_consensus_revenue_analyst_count"]
        is None
    )


def test_relative_peer_metrics_rejects_implausible_yahoo_multiples(monkeypatch):
    # Reproduces the ASML bug: Yahoo returns a bookValue/enterpriseValue
    # computed against a mismatched share basis, producing P/B ~1479x and
    # EV/EBITDA ~2754x. Those must be rejected as implausible and replaced
    # with the SEC-derived fallback rather than published as-is.
    monkeypatch.setattr(valuation, "get_yahoo_quote", lambda symbol: {
        "marketCap": 668_714_270_720.0,
        "regularMarketPrice": 1740.99,
        "trailingPE": 58.13,
        "priceToBook": 1479.31,
        "enterpriseToEbitda": 2753.86,
        "epsTrailingTwelveMonths": 29.95,
    })
    monkeypatch.setattr(valuation, "get_yahoo_quote_summary_metrics", lambda symbol: {})
    monkeypatch.setattr(
        valuation,
        "_finnhub_peer_fallback",
        lambda symbol: {"pe": None, "pb": None, "ev_ebitda": None, "warnings": []},
    )
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda symbol: {
        "net_income": 11_110_417_411.0,
        "bv_0": 22_675_685_095.0,
        "target_ebitda": 14_801_017_487.0,
        "total_debt": 5_076_771_891.0,
        "cash": 15_402_821_165.0,
    })

    metrics = valuation._load_relative_peer_metrics("ASML")

    assert metrics["pe"] == pytest.approx(58.13, rel=1e-3)
    assert metrics["pb"] < 100.0
    assert metrics["ev_ebitda"] < 150.0
    assert metrics["metric_sources"]["pb"] == "SEC-derived"
    assert metrics["metric_sources"]["ev_ebitda"] == "SEC-derived"
    assert metrics["rejected_provider_values"] == {
        "pb": "Yahoo quote/summary",
        "ev_ebitda": "Yahoo quote/summary",
    }


def test_relative_endpoint_recalculates_only_with_available_selected_peers(monkeypatch):
    peers = [
        {"symbol": "AAA", "pe": 10.0, "pb": 1.0, "ev_ebitda": 5.0},
        {"symbol": "BBB", "pe": 30.0, "pb": 3.0, "ev_ebitda": 15.0},
        {"symbol": "CCC", "pe": 50.0, "pb": 5.0, "ev_ebitda": 25.0},
    ]
    monkeypatch.setattr(
        valuation,
        "get_valuation_inputs",
        lambda ticker: {
            "target_eps": 2.0,
            "target_bvps": 10.0,
            "target_ebitda": 100.0,
            "total_debt": 0.0,
            "cash": 0.0,
            "shares_outstanding": 10.0,
            "adr_ratio": 1.0,
            "company_profile": {"sector": "Technology"},
        },
    )
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {"current_price": 50.0})
    monkeypatch.setattr(valuation, "build_relative_peers", lambda ticker: peers)

    all_peers = valuation.get_relative("MSFT")
    selected = valuation.get_relative("MSFT", included_peer_symbols=["AAA", "BBB"])

    assert all_peers["computed_fair_value"] == pytest.approx(80.0)
    assert all_peers["underlying_assumptions"]["peer_selection_basis"] == "all_available_peers"
    assert selected["computed_fair_value"] == pytest.approx(160 / 3)
    assert selected["underlying_assumptions"]["available_peers"] == peers
    assert selected["underlying_assumptions"]["included_peer_symbols"] == ["AAA", "BBB"]
    assert selected["underlying_assumptions"]["peer_selection_basis"] == "user_selected_available_peers"


def test_relative_endpoint_rejects_unknown_or_empty_peer_selection(monkeypatch):
    monkeypatch.setattr(
        valuation,
        "get_valuation_inputs",
        lambda ticker: {
            "target_eps": 2.0,
            "target_bvps": 10.0,
            "target_ebitda": 100.0,
            "total_debt": 0.0,
            "cash": 0.0,
            "shares_outstanding": 10.0,
            "adr_ratio": 1.0,
            "company_profile": {"sector": "Technology"},
        },
    )
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {"current_price": 50.0})
    monkeypatch.setattr(
        valuation,
        "build_relative_peers",
        lambda ticker: [{"symbol": "AAA", "pe": 10.0, "pb": 1.0, "ev_ebitda": 5.0}],
    )

    unknown = valuation.get_relative("MSFT", included_peer_symbols=["ZZZ"])
    empty = valuation.get_relative("MSFT", included_peer_symbols=[])

    assert unknown["valuation_status"] == "INVALID_INPUT"
    assert unknown["underlying_assumptions"]["error_code"] == "VALUATION_INPUT_INVALID"
    assert empty["valuation_status"] == "INVALID_INPUT"
    assert empty["underlying_assumptions"]["error_code"] == "VALUATION_INPUT_INVALID"


def test_dcf_endpoint_validates_missing_cyclical_metadata_safely(monkeypatch):
    def fake_inputs(ticker: str):
        return {
            "sic_code": "2911",
            "valuation_methodology": ValuationMethodology.CYCLICAL.value,
            "capex": 80.0,
            "base_revenue": 1000.0,
            "ebit_margin": None,
            "effective_tax_rate": 0.20,
            "shares_outstanding": 10.0,
            "total_debt": 100.0,
            "cash": 50.0,
            "stage_1_growth_rate_default": 0.05,
            "depreciation_amortization": 30.0,
            "change_in_nwc": 10.0,
            "operating_margin_history": [],
            "adaptive_valuation_data": {"sic_code": "2911"},
        }

    monkeypatch.setattr(valuation, "get_valuation_inputs", fake_inputs)
    monkeypatch.setattr(
        valuation,
        "get_valuation_telemetry",
        lambda ticker: {"risk_free_rate": 0.04, "market_risk_premium": 0.055},
    )

    payload = valuation.get_dcf("XOM", wacc=0.09, projection_years=3)
    validated = ValuationResponse.model_validate(payload)

    assert validated.valuation_status == "MISSING_INPUT"
    assert validated.valuation_methodology == "Normalized Median DCF"
    assert validated.engine_metadata == {}
    assert validated.projections == []


@valuator_test(
    epic="DCF",
    feature="Sector Routing",
    story="Cyclical Engine History",
    priority="P1",
    severity="normal",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-DCF-003"
)
def test_dcf_endpoint_cyclical_uses_margin_history_without_current_ebit_margin(monkeypatch):
    def fake_inputs(ticker: str):
        return {
            "sic_code": "2911",
            "valuation_methodology": ValuationMethodology.CYCLICAL.value,
            "capex": 80.0,
            "base_revenue": 1000.0,
            "ebit_margin": None,
            "effective_tax_rate": 0.20,
            "shares_outstanding": 10.0,
            "total_debt": 100.0,
            "cash": 50.0,
            "stage_1_growth_rate_default": 0.05,
            "depreciation_amortization": 30.0,
            "change_in_nwc": 10.0,
            "operating_margin_history": [
                {"value": 0.04},
                {"value": 0.12},
                {"value": 0.08},
            ],
            "adaptive_valuation_data": {
                "sic_code": "2911",
                "revenue_history": [
                    {"value": 900.0},
                    {"value": 1000.0},
                ],
            },
        }

    monkeypatch.setattr(valuation, "get_valuation_inputs", fake_inputs)
    monkeypatch.setattr(
        valuation,
        "get_valuation_telemetry",
        lambda ticker: {"risk_free_rate": 0.04, "market_risk_premium": 0.055},
    )

    payload = valuation.get_dcf("XOM", wacc=0.09, projection_years=3)
    validated = ValuationResponse.model_validate(payload)

    assert validated.valuation_status == "CALCULATED"
    assert validated.valuation_methodology == "Normalized Median DCF"
    assert validated.engine_metadata["10_year_historical_median_margin"] == 0.08
    assert validated.projections[0].unlevered_free_cash_flow is not None
    assert_sensitivity_center_matches_overview(payload)


def test_dcf_endpoint_standard_uses_cost_of_equity_wacc_fallback(monkeypatch):
    def fake_inputs(ticker: str):
        return {
            "sic_code": "5331",
            "valuation_methodology": ValuationMethodology.STANDARD.value,
            "capex": 80.0,
            "base_revenue": 1000.0,
            "ebit_margin": 0.04,
            "effective_tax_rate": 0.20,
            "shares_outstanding": 10.0,
            "total_debt": 100.0,
            "cash": 50.0,
            "stage_1_growth_rate_default": 0.05,
            "depreciation_amortization": 30.0,
            "change_in_nwc": 10.0,
            "interest_expense": None,
            "adaptive_valuation_data": {
                "sic_code": "5331",
                "revenue_history": [
                    {"value": 800.0, "end": "2022-01-31"},
                    {"value": 900.0, "end": "2023-01-31"},
                    {"value": 1000.0, "end": "2024-01-31"},
                ],
            },
            "operating_margin_history": [
                {"value": 0.035, "end": "2023-01-31"},
                {"value": 0.040, "end": "2024-01-31"},
            ],
        }

    monkeypatch.setattr(valuation, "get_valuation_inputs", fake_inputs)
    monkeypatch.setattr(
        valuation,
        "get_valuation_telemetry",
        lambda ticker: {
            "market_cap": 1000.0,
            "cost_of_equity": 0.09,
            "risk_free_rate": 0.04,
            "market_risk_premium": 0.055,
            "current_price": 60.0,
        },
    )

    payload = valuation.get_dcf("WMT", projection_years=3)
    validated = ValuationResponse.model_validate(payload)

    assert validated.valuation_status == "CALCULATED"
    assert validated.monte_carlo_results.iteration_count == 10_000
    assert validated.monte_carlo_results.valid_sample_count == 10_000
    assert len(validated.monte_carlo_results.histogram_bins) == 40
    assert validated.monte_carlo_results.bear_p10 <= validated.monte_carlo_results.base_p50
    assert validated.monte_carlo_results.base_p50 <= validated.monte_carlo_results.bull_p90
    assert validated.implied_expectations["solver_status"] == "converged"
    assert validated.implied_expectations["implied_revenue_cagr"] is not None
    assert validated.implied_expectations["implied_operating_margin"] is not None
    assumptions = payload["underlying_assumptions"]
    assert assumptions["wacc"] == 0.09
    assert assumptions["wacc_basis"] == "cost_of_equity_fallback_debt_metrics_unavailable"
    assert assumptions["wacc_components"]["fallback_reason"]
    assert_sensitivity_center_matches_overview(payload)

    targeted = valuation.get_dcf(
        "WMT",
        implied_target_price=55.0,
        projection_years=3,
    )
    assert targeted["implied_expectations"]["target_price"] == 55.0
    assert targeted["implied_expectations"]["model_fair_value"] == pytest.approx(55.0, abs=0.01)

    invalid = valuation.get_dcf(
        "WMT",
        discount_rate=0.02,
        perpetual_growth_rate=0.02,
        projection_years=3,
    )
    assert invalid["valuation_status"] == "INVALID_INPUT"
    assert invalid["underlying_assumptions"]["error_code"] == "VALUATION_INPUT_INVALID"


def test_dcf_endpoint_returns_unavailable_for_non_positive_equity_value(monkeypatch):
    # A model can complete without error yet produce a non-positive equity
    # value (e.g. reinvestment exceeds NOPAT for enough of the horizon that
    # discounted cash flow never recovers). AGENTS.md forbids presenting a
    # placeholder/impossible number as a real fair value, so this must
    # surface as UNAVAILABLE with a machine-readable reason rather than a
    # negative computed_fair_value under status CALCULATED.
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "sic_code": "5331",
        "valuation_methodology": ValuationMethodology.STANDARD.value,
        "capex": 80.0,
        "base_revenue": 1000.0,
        "ebit_margin": 0.10,
        "effective_tax_rate": 0.20,
        "shares_outstanding": 10.0,
        "total_debt": 100_000.0,  # far exceeds any plausible enterprise value
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
    assumptions = payload["underlying_assumptions"]
    assert assumptions["unavailable_reason_code"] == "NEGATIVE_OR_ZERO_EQUITY_VALUE"
    assert "reinvestment" in assumptions["unavailable_reason"].lower()
    assert assumptions["equity_value"] <= 0


def test_dcf_skips_monte_carlo_when_historical_volatility_inputs_are_missing(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "sic_code": "5331", "capex": 80.0, "base_revenue": 1000.0,
        "ebit_margin": 0.10, "effective_tax_rate": 0.20,
        "shares_outstanding": 10.0, "total_debt": 100.0, "cash": 50.0,
        "stage_1_growth_rate_default": 0.05, "depreciation_amortization": 30.0,
        "change_in_nwc": 10.0, "interest_expense": None,
        "operating_margin_history": [],
        "adaptive_valuation_data": {"revenue_history": []},
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "market_cap": 1000.0, "cost_of_equity": 0.09,
        "risk_free_rate": 0.04, "market_risk_premium": 0.055,
        "current_price": 60.0,
    })

    payload = valuation.get_dcf("NOHISTORY", projection_years=3)

    assert payload["valuation_status"] == "CALCULATED"
    assert payload["monte_carlo_results"] == {}
    warnings = payload["underlying_assumptions"]["computational_warnings"]
    assert any("insufficient comparable annual history" in warning for warning in warnings)


def test_zero_dividend_ddm_is_explicitly_inapplicable(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "dividends_paid": 0.0,
        "shares_outstanding": 100.0,
        "historical_dividends": [0.0, 0.0],
        "net_income": None,
        "adr_ratio": 1.0,
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "cost_of_equity": 0.10,
        "current_price": None,
    })

    payload = valuation.get_ddm("NOPAYOUT", historical_dividends=[0.0, 0.0])

    assert payload["valuation_status"] == "INAPPLICABLE"
    assert payload["computed_fair_value"] is None
    assert payload["underlying_assumptions"]["is_ddm_applicable"] is False
    assert any(
        "No sourced dividend" in reason
        for reason in payload["underlying_assumptions"]["applicability_reasons"]
    )


def test_applicable_ddm_uses_standard_calculated_response_status(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "dividends_paid": 200.0,
        "shares_outstanding": 100.0,
        "historical_dividends": [160.0, 168.0, 176.0],
        "net_income": 400.0,
        "adr_ratio": 1.0,
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "cost_of_equity": 0.10,
        "current_price": 40.0,
    })
    monkeypatch.setattr(valuation, "get_yahoo_quote", lambda ticker: {
        "regularMarketPrice": 40.0,
    })

    payload = valuation.get_ddm("DIVIDEND", historical_dividends=None)

    assert payload["valuation_status"] == "CALCULATED"
    assert payload["computed_fair_value"] is not None
    assert payload["underlying_assumptions"]["status"] == "APPLICABLE"
    assert payload["underlying_assumptions"]["is_ddm_applicable"] is True


def test_dcf_caps_cost_of_debt_after_comparable_unit_normalization(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "sic_code": "5331", "capex": 80.0, "base_revenue": 1000.0,
        "ebit_margin": 0.10, "effective_tax_rate": 0.20,
        "shares_outstanding": 10.0, "total_debt": 100.0, "cash": 50.0,
        "stage_1_growth_rate_default": 0.05, "depreciation_amortization": 30.0,
        "change_in_nwc": 10.0, "interest_expense": 200.0,
        "adaptive_valuation_data": {"revenue_history": [{"value": 900.0}, {"value": 1000.0}]},
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "market_cap": 900.0, "cost_of_equity": 0.09, "risk_free_rate": 0.04,
        "market_risk_premium": 0.055, "current_price": 60.0,
    })
    payload = valuation.get_dcf("TEST", projection_years=3)
    components = payload["underlying_assumptions"]["wacc_components"]
    assert components["raw_cost_of_debt"] == 2.0
    assert components["cost_of_debt"] == 0.20
    assert components["cost_of_debt_capped"] is True


def test_asset_based_requires_reported_goodwill_and_intangibles(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "total_assets": 1000.0, "total_liabilities": 400.0,
        "goodwill": None, "intangible_assets": None, "shares_outstanding": 10.0,
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {})
    payload = valuation.get_asset_based("FPI")
    assert payload["valuation_status"] == "MISSING_INPUT"
    assumptions = payload["underlying_assumptions"]
    assert assumptions["missing_inputs"] == ["goodwill", "intangible_assets"]
    assert "computed_fair_value" not in assumptions


def test_direct_filing_asset_cell_wins_over_vendor_zero_placeholder():
    financials = {
        "quarterly": {
            "balance_sheet": {
                "rows": [
                    {
                        "id": "intangible_assets",
                        "cells": {
                            "2025-12-31": {
                                "value": 124_000_000.0,
                                "taxonomy": "us-gaap",
                                "concept": "IntangibleAssetsNetExcludingGoodwill",
                                "period_end": "2025-12-31",
                                "filed": "2026-01-29",
                            },
                            "FMP_Q_2026-06-30": {
                                "value": 0.0,
                                "taxonomy": "FMP",
                                "concept": "intangible_assets",
                                "period_end": "2026-06-30",
                            },
                        },
                    }
                ]
            }
        }
    }

    cell = valuation._latest_direct_filing_cell(
        financials,
        "balance_sheet",
        "intangible_assets",
    )

    assert cell is not None
    assert cell["value"] == 124_000_000.0
    assert cell["concept"] == "IntangibleAssetsNetExcludingGoodwill"


def test_vendor_asset_cell_rejects_one_period_zero_placeholder():
    financials = {
        "quarterly": {
            "balance_sheet": {
                "rows": [
                    {
                        "id": "intangible_assets",
                        "cells": {
                            "FMP_Q_2026-03-31": {
                                "value": 18_749_220_000.0,
                                "taxonomy": "FMP",
                                "period_end": "2026-03-31",
                            },
                            "FMP_Q_2026-06-30": {
                                "value": 0.0,
                                "taxonomy": "FMP",
                                "period_end": "2026-06-30",
                            },
                        },
                    }
                ]
            }
        }
    }

    cell, basis, rejected_period = valuation._latest_reliable_vendor_asset_cell(
        financials,
        "intangible_assets",
    )

    assert cell is not None
    assert cell["value"] == 18_749_220_000.0
    assert basis == "prior_vendor_statement_after_unconfirmed_zero"
    assert rejected_period == "2026-06-30"


def test_vendor_asset_cell_accepts_confirmed_consecutive_zero_periods():
    financials = {
        "quarterly": {
            "balance_sheet": {
                "rows": [
                    {
                        "id": "goodwill",
                        "cells": {
                            "FMP_Q_2025-12-31": {
                                "value": 10.0,
                                "taxonomy": "FMP",
                                "period_end": "2025-12-31",
                            },
                            "FMP_Q_2026-03-31": {
                                "value": 0.0,
                                "taxonomy": "FMP",
                                "period_end": "2026-03-31",
                            },
                            "FMP_Q_2026-06-30": {
                                "value": 0.0,
                                "taxonomy": "FMP",
                                "period_end": "2026-06-30",
                            },
                        },
                    }
                ]
            }
        }
    }

    cell, basis, rejected_period = valuation._latest_reliable_vendor_asset_cell(
        financials,
        "goodwill",
    )

    assert cell is not None
    assert cell["value"] == 0.0
    assert basis == "latest_vendor_statement"
    assert rejected_period is None


def test_asset_based_exposes_direct_filing_basis_and_timestamp(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "total_assets": 1_000.0,
        "total_liabilities": 400.0,
        "total_liabilities_basis": "reported_total_liabilities",
        "goodwill": 25.0,
        "goodwill_basis": "sec_company_facts:Goodwill",
        "goodwill_source_timestamp": "2025-12-31",
        "intangible_assets": 12.0,
        "intangible_assets_basis": "sec_company_facts:IntangibleAssetsNetExcludingGoodwill",
        "intangible_assets_source_timestamp": "2025-12-31",
        "shares_outstanding": 10.0,
        "adr_ratio": 1.0,
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "current_price": 50.0,
    })

    payload = valuation.get_asset_based("TSLA")
    assumptions = payload["underlying_assumptions"]

    assert payload["valuation_status"] == "CALCULATED"
    assert assumptions["goodwill_basis"] == "sec_company_facts:Goodwill"
    assert assumptions["goodwill_source_timestamp"] == "2025-12-31"
    assert assumptions["intangible_assets_basis"] == (
        "sec_company_facts:IntangibleAssetsNetExcludingGoodwill"
    )
    assert assumptions["intangible_assets_source_timestamp"] == "2025-12-31"
