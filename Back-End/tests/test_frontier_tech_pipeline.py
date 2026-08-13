import pytest
from time import monotonic

from app.api.routes import valuation
from app.providers.sec import _resolve_common_shares_outstanding
from app.services.sotp_configs import get_sotp_config, resolve_sotp_profile
from app.services.dynamic_valuation_router import DynamicSOTPReverseDCFEngine
from app.services.valuation_engines import calculate_standard_driver_dcf


def _fact(value, *, end="2025-12-31", accession="0000000000-25-000001"):
    return {
        "val": value,
        "end": end,
        "form": "10-K",
        "filed": "2026-02-01",
        "accn": accession,
    }


def test_sec_share_resolver_uses_us_gaap_aggregate_when_dei_is_missing():
    us_gaap = {
        "CommonStockSharesOutstanding": {
            "units": {"shares": [_fact(12_116_000_000)]}
        }
    }

    result = _resolve_common_shares_outstanding(
        {"us-gaap": us_gaap}, us_gaap, {}
    )

    assert result["value"] == 12_116_000_000
    assert result["status"] == "reported"
    assert result["basis"] == "aggregate SEC fact: CommonStockSharesOutstanding"


def test_sec_share_resolver_sums_matching_core_share_classes_without_aggregate():
    custom = {
        "ClassACommonStockSharesOutstanding": {
            "units": {"shares": [_fact(5_800_000_000)]}
        },
        "ClassCCommonStockSharesOutstanding": {
            "units": {"shares": [_fact(5_900_000_000)]}
        },
    }

    result = _resolve_common_shares_outstanding({"company": custom}, {}, {})

    assert result["value"] == 11_700_000_000
    assert result["status"] == "derived"
    assert len(result["input_refs"]) == 2


@pytest.mark.parametrize(
    ("classification", "methodology", "expected"),
    [
        ({"industry": "Software - Infrastructure", "businessTags": ["Cloud Infrastructure"]}, None, "software"),
        ({"industry": "Semiconductors", "businessTags": ["Accelerated Compute"]}, None, "semiconductors"),
        ({"sicDescription": "Motor Vehicles & Passenger Car Bodies", "businessTags": ["Autonomous Driving"]}, None, "automotive"),
        (None, "Capitalized R&D DCF", "frontier-tech"),
    ],
)
def test_frontier_tech_profile_is_classification_driven(classification, methodology, expected):
    assert resolve_sotp_profile(
        classification=classification,
        methodology=methodology,
    ) == expected
    config = get_sotp_config(
        classification=classification,
        methodology=methodology,
    )
    assert config["profile"] == expected
    assert config["segment_source"] == "single_segment_fallback_unquantified_classification"
    assert config["segments"] == [{
        "name": "Core Business", "base_revenue_fraction": 1.0, "is_high_growth": False,
    }]


def test_fifteen_year_scenarios_generate_distinct_margin_curves():
    common = {
        "base_revenue": 100_000_000_000,
        "ebit_margin": 0.08,
        "tax_rate": 0.20,
        "capex": 8_000_000_000,
        "depreciation_amortization": 5_000_000_000,
        "change_in_nwc": 1_000_000_000,
        "shares_outstanding": 3_000_000_000,
        "total_debt": 5_000_000_000,
        "cash_and_equivalents": 20_000_000_000,
        "wacc": 0.10,
        "stage_1_growth_rate": 0.12,
        "perpetual_growth_rate": 0.02,
        "projection_years": 15,
    }

    results = {
        scenario: calculate_standard_driver_dcf(**common, scenario=scenario)
        for scenario in ("bear", "base", "bull")
    }
    curves = {
        scenario: [row["ebit_margin"] for row in result["revenue_projections"]]
        for scenario, result in results.items()
    }

    assert all(len(curve) == 15 for curve in curves.values())
    assert curves["bear"] != curves["base"]
    assert curves["base"] != curves["bull"]
    assert results["bear"]["harvest_start_year"] == 4
    assert results["base"]["harvest_start_year"] == 6
    assert results["bull"]["harvest_start_year"] == 8
    assert curves["bear"][-1] < curves["base"][-1] < curves["bull"][-1]


def test_sotp_reverse_dcf_engine_defaults_to_fifteen_year_horizon():
    assert DynamicSOTPReverseDCFEngine().periods == 15


def test_tech_endpoint_activates_fifteen_year_sotp_and_reactive_scenarios(monkeypatch):
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: {
        "sic_code": "7372",
        "sic_description": "Prepackaged Software",
        "finnhub_industry": "Software - Infrastructure",
        "cfo": 90_000_000_000,
        "capex": 30_000_000_000,
        "base_revenue": 250_000_000_000,
        "ebit_margin": 0.42,
        "effective_tax_rate": 0.18,
        "reinvestment_rate": 0.20,
        "shares_outstanding": 7_500_000_000,
        "total_debt": 40_000_000_000,
        "cash": 80_000_000_000,
        "bv_0": 200_000_000_000,
        "stage_1_growth_rate_default": 0.12,
        "operating_income": 105_000_000_000,
        "depreciation_amortization": 20_000_000_000,
        "change_in_nwc": 2_000_000_000,
        "r_and_d_history": [{"value": 24_000_000_000}, {"value": 27_000_000_000}],
        "operating_margin_history": [{"value": 0.38}, {"value": 0.42}],
        "adaptive_valuation_data": {
            "revenue_history": [{"value": 220_000_000_000}, {"value": 250_000_000_000}],
        },
    })
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: {
        "current_price": 400.0,
        "market_cap": 3_000_000_000_000,
        "risk_free_rate": 0.04,
        "market_risk_premium": 0.055,
        "cost_of_equity": 0.09,
    })
    monkeypatch.setattr(valuation, "get_cached_company_classification", lambda ticker: None)
    monkeypatch.setattr(valuation, "run_monte_carlo_simulation", lambda **kwargs: {})
    monkeypatch.setattr(valuation, "calculate_implied_expectations", lambda **kwargs: {})

    payload = valuation.get_dcf("TECH", wacc=0.09, projection_years=7)

    assert payload["valuation_status"] == "CALCULATED"
    assert payload["underlying_assumptions"]["projection_years"] == 15
    assert payload["reverse_dcf_sotp"]["is_active"] is False
    assert payload["reverse_dcf_sotp"]["classification_profile"] == "software"
    assert payload["reverse_dcf_sotp"]["horizon_years"] == 15
    assert payload["reverse_dcf_sotp"]["solver_available"] is False
    assert payload["reverse_dcf_sotp"]["requested_target_price"] == 400.0
    assert payload["reverse_dcf_sotp"]["model_fair_value"] == payload["computed_fair_value"]
    assert payload["reverse_dcf_sotp"]["segments"] == []
    assert payload["sotp_breakdown"]["status"] == "UNAVAILABLE"
    assert payload["sotp_breakdown"]["calculated_price"] is None
    scenarios = payload["forward_dcf"]["scenarios"]
    assert all(len(scenarios[name]["projections"]) == 15 for name in ("bear", "base", "bull"))
    margins = {
        name: [row["ebit_margin"] for row in scenarios[name]["projections"]]
        for name in ("bear", "base", "bull")
    }
    assert margins["bear"] != margins["base"] != margins["bull"]


def test_relative_peer_builder_does_not_reuse_empty_cache(monkeypatch):
    calls = []
    valuation._relative_peer_cache["EMPTY"] = (monotonic(), [])
    monkeypatch.setattr(
        valuation,
        "_default_relative_peer_specs",
        lambda ticker: calls.append(ticker) or [],
    )

    assert valuation.build_relative_peers("EMPTY") == []
    assert calls == ["EMPTY"]


def test_relative_peer_specs_use_curated_fallback_when_providers_return_no_peers(monkeypatch):
    classification = type("Classification", (), {"competitors": []})()
    monkeypatch.setattr(
        valuation,
        "get_company_classification",
        lambda ticker: classification,
    )

    specs = valuation._default_relative_peer_specs("tsla")

    assert [spec["symbol"] for spec in specs] == ["GM", "F", "RIVN", "BYD"]
    assert specs[-1]["source_symbol"] == "1211.HK"
    assert all(spec["selection_source"] == "Curated provider-outage fallback" for spec in specs)


def test_relative_peer_specs_reject_unscored_provider_candidates(monkeypatch):
    def fallback_peer(ticker):
        return type("Peer", (), {
            "ticker": ticker,
            "overlap_score": 50.0,
            "reason": "Fallback peer due to unavailable AI scoring",
        })()

    classification = type("Classification", (), {
        "competitors": [
            fallback_peer("CJET"),
            fallback_peer("F"),
            fallback_peer("GELHY"),
            fallback_peer("GM"),
        ],
    })()
    monkeypatch.setattr(
        valuation,
        "get_company_classification",
        lambda ticker: classification,
    )

    specs = valuation._default_relative_peer_specs("TSLA")

    assert [spec["symbol"] for spec in specs] == ["GM", "F", "RIVN", "BYD"]
    assert specs[-1]["source_symbol"] == "1211.HK"


def test_relative_peer_specs_keep_sourced_candidates_without_curated_fallback(monkeypatch):
    def fallback_peer(ticker):
        return type("Peer", (), {
            "ticker": ticker,
            "overlap_score": 50.0,
            "reason": "Fallback peer due to unavailable AI scoring",
        })()

    classification = type("Classification", (), {
        "competitors": [
            fallback_peer("BUD"),
            fallback_peer("CCEP"),
            fallback_peer("COKE"),
            fallback_peer("KDP"),
        ],
    })()
    monkeypatch.setattr(
        valuation,
        "get_company_classification",
        lambda ticker: classification,
    )

    specs = valuation._default_relative_peer_specs("KO")

    assert [spec["symbol"] for spec in specs] == ["BUD", "CCEP", "COKE", "KDP"]
    assert all(spec["overlap_score"] is None for spec in specs)
    assert all(
        spec["selection_source"] == "FMP stock-peer fallback (AI scoring unavailable)"
        for spec in specs
    )
