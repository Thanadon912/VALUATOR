from app.providers.sec import _latest_annual_filing, _latest_quarterly_filing
from app.providers.sec_financials import ANNUAL_FORMS, QUARTERLY_FORMS
from app.services.international import derive_adr_ratio, fetch_usd_fx_rate, country_risk_premium
from app.services.telemetry import calculate_cost_of_equity
from app.services.valuation_engines import (
    calculate_residual_income_valuation,
    normalize_equity_value_per_traded_share,
)
from app.api.routes.valuation import (
    _normalize_financial_payloads_to_usd,
    _normalize_rnd_history_to_usd,
)


def _submissions(forms):
    return {"filings": {"recent": {
        "form": forms,
        "accessionNumber": [f"acc-{i}" for i in range(len(forms))],
        "primaryDocument": [f"doc-{i}.htm" for i in range(len(forms))],
        "reportDate": ["2025-12-31"] * len(forms),
        "filingDate": ["2026-03-01"] * len(forms),
    }}}


def test_sec_form_router_accepts_fpi_annual_and_periodic_forms():
    assert {"20-F", "40-F"} <= ANNUAL_FORMS
    assert "6-K" in QUARTERLY_FORMS
    assert _latest_annual_filing(_submissions(["8-K", "20-F"]))["form"] == "20-F"
    assert _latest_annual_filing(_submissions(["40-F"]))["form"] == "40-F"
    assert _latest_quarterly_filing(_submissions(["6-K"]))["form"] == "6-K"


def test_adr_ratio_and_fair_value_use_ordinary_shares_per_adr():
    assert derive_adr_ratio(25_900_000_000, 5_180_000_000) == 5.0
    # shares_outstanding is already the number of listed ADRs, so we do not multiply by adr_ratio again
    assert normalize_equity_value_per_traded_share(1_000, 100, 5) == 10.0


def test_residual_income_applies_adr_ratio_to_final_equity_value():
    ordinary = calculate_residual_income_valuation(1_000, 100, 100, 0.09)
    adr = calculate_residual_income_valuation(1_000, 100, 100, 0.09, adr_ratio=5)
    # The engines now treat shares_outstanding as the listed shares natively,
    # so adr_ratio doesn't act as a blind multiplier anymore.
    assert adr["computed_fair_value"] == ordinary["computed_fair_value"]
    assert adr["adr_ratio"] == 5


def test_fx_rate_uses_latest_non_null_daily_close(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"chart": {"result": [{"timestamp": [100, 200], "indicators": {"quote": [{"close": [None, 0.031]}]}}]}}
    monkeypatch.setattr("app.services.international.httpx.get", lambda *args, **kwargs: Response())
    result = fetch_usd_fx_rate("TWD")
    assert result["rate"] == 0.031
    assert result["valuation_currency"] == "USD"
    assert "TWDUSD=X" in result["source"]


def test_cost_of_equity_adds_domicile_country_risk_premium():
    base = calculate_cost_of_equity(1.0, 0.04, 0.055)
    taiwan = country_risk_premium("TW")
    adjusted = calculate_cost_of_equity(1.0, 0.04, 0.055, taiwan["country_risk_premium"])
    assert adjusted == base + 0.0075
    assert country_risk_premium("unknown") is None


def test_rnd_history_uses_same_fx_rate_and_unit_for_every_year():
    history = [
        {"value": 100, "unit": "TWD", "end": "2022-12-31", "form": "20-F"},
        {"value": 120, "unit": "TWD", "end": "2023-12-31", "form": "20-F"},
        {"value": 150, "unit": "TWD", "end": "2024-12-31", "form": "20-F"},
    ]
    normalized, metadata = _normalize_rnd_history_to_usd(
        history, "TWD", {"rate": 0.031, "source": "test FX"}
    )
    assert [row["value"] for row in normalized] == [3.1, 3.7199999999999998, 4.65]
    assert {row["unit"] for row in normalized} == {"USD"}
    assert {row["fx_rate"] for row in normalized} == {0.031}
    assert metadata["observation_count"] == 3


def test_mixed_statement_units_are_normalized_per_cell_before_wacc(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.valuation.fetch_usd_fx_rate",
        lambda unit: {
            "reported_currency": unit, "valuation_currency": "USD",
            "rate": 1.0 if unit == "USD" else 0.031,
            "source": f"{unit} test rate", "as_of": "2026-07-12",
        },
    )
    income = {"interest_expense": {"value": 10, "unit": "USD"}}
    balance = {"total_debt": {"value": 1000, "unit": "TWD"}}
    result = _normalize_financial_payloads_to_usd(income, balance)
    assert income["interest_expense"]["value"] == 10
    assert balance["total_debt"]["value"] == 31
    assert balance["total_debt"]["reported_unit"] == "TWD"
    assert balance["total_debt"]["unit"] == "USD"
    assert result["status"] == "normalized"
