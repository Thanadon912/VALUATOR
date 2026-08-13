from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal


DcfValueStatus = Literal[
    "reported",
    "calculated",
    "suggested",
    "user_override",
    "normalized",
    "unavailable",
    "invalid",
    "estimated_with_warning",
]

ReinvestmentMethod = Literal[
    "direct_fcff_drivers",
    "sales_to_capital",
    "roic_based",
]


@dataclass(frozen=True)
class DcfSourceLineage:
    provider: str | None = None
    source_url: str | None = None
    source_timestamp: str | None = None
    fetched_at: str | None = None
    filing_date: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    accession_number: str | None = None
    form_type: str | None = None
    source_tag: str | None = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "source_url": self.source_url,
            "source_timestamp": self.source_timestamp,
            "fetched_at": self.fetched_at,
            "filing_date": self.filing_date,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "source_tag": self.source_tag,
        }


@dataclass(frozen=True)
class DcfValue:
    name: str
    value: float | None
    status: DcfValueStatus
    unit: str | None = None
    currency: str | None = None
    basis: str | None = None
    input_refs: tuple[str, ...] = ()
    lineage: DcfSourceLineage = field(default_factory=DcfSourceLineage)
    confidence: Literal["high", "medium", "low", "insufficient"] | None = None
    warnings: tuple[str, ...] = ()
    user_overridden: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "status": self.status,
            "unit": self.unit,
            "currency": self.currency,
            "basis": self.basis,
            "input_refs": list(self.input_refs),
            "lineage": self.lineage.to_dict(),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "user_overridden": self.user_overridden,
        }


@dataclass(frozen=True)
class DcfAssumptions:
    revenue_growth_rate: float
    free_cash_flow_margin: float
    discount_rate: float
    terminal_growth_rate: float
    forecast_years: int


@dataclass(frozen=True)
class DcfInputs:
    base_revenue: float
    cash_and_equivalents: float
    total_debt: float
    shares_outstanding: float
    assumptions: DcfAssumptions


@dataclass(frozen=True)
class DcfForecastAssumptions:
    forecast_years: int
    revenue_growth_rates: tuple[DcfValue, ...]
    ebit_margin: DcfValue
    tax_rate: DcfValue
    depreciation_amortization_percent_of_revenue: DcfValue
    capital_expenditure_percent_of_revenue: DcfValue
    change_in_nwc_percent_of_revenue: DcfValue
    wacc: DcfValue
    terminal_growth_rate: DcfValue
    terminal_wacc: DcfValue | None = None
    terminal_value_min_spread: float = 0.005
    ebit_margin_by_year: tuple[DcfValue, ...] = ()
    tax_rate_by_year: tuple[DcfValue, ...] = ()
    depreciation_amortization_percent_of_revenue_by_year: tuple[DcfValue, ...] = ()
    capital_expenditure_percent_of_revenue_by_year: tuple[DcfValue, ...] = ()
    change_in_nwc_percent_of_revenue_by_year: tuple[DcfValue, ...] = ()
    reinvestment_method: ReinvestmentMethod = "direct_fcff_drivers"
    sales_to_capital_by_year: tuple[DcfValue, ...] = ()
    roic_by_year: tuple[DcfValue, ...] = ()
    stock_based_compensation_percent_of_revenue_by_year: tuple[DcfValue, ...] = ()
    share_dilution_rate_by_year: tuple[DcfValue, ...] = ()


@dataclass(frozen=True)
class DcfEquityBridgeInputs:
    cash_and_equivalents: DcfValue
    total_debt: DcfValue
    diluted_shares: DcfValue
    marketable_securities: DcfValue | None = None
    non_operating_assets: DcfValue | None = None
    preferred_stock: DcfValue | None = None
    minority_interest: DcfValue | None = None
    other_claims: DcfValue | None = None


@dataclass(frozen=True)
class DcfStartingBasis:
    basis_type: Literal["latest_ttm", "latest_fiscal_year", "normalized"]
    selected_by: Literal["system", "user"] = "system"
    period_start: str | None = None
    period_end: str | None = None
    calculation_method: str | None = None
    historical_revenue: float | None = None
    historical_ebit: float | None = None
    historical_ebit_margin: float | None = None
    historical_nopat: float | None = None
    historical_free_cash_flow: float | None = None
    source_facts: tuple[dict, ...] = ()
    data_quality: Literal["high", "medium", "low", "insufficient"] = "insufficient"
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    user_overridden: bool = False

    def to_dict(self) -> dict:
        return {
            "basis_type": self.basis_type,
            "selected_by": self.selected_by,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "calculation_method": self.calculation_method,
            "historical_revenue": self.historical_revenue,
            "historical_ebit": self.historical_ebit,
            "historical_ebit_margin": self.historical_ebit_margin,
            "historical_nopat": self.historical_nopat,
            "historical_free_cash_flow": self.historical_free_cash_flow,
            "source_facts": list(self.source_facts),
            "data_quality": self.data_quality,
            "reason_codes": list(self.reason_codes),
            "warnings": list(self.warnings),
            "user_overridden": self.user_overridden,
        }


@dataclass(frozen=True)
class NormalizedDcfInputs:
    ticker: str
    currency: str
    base_revenue: DcfValue
    assumptions: DcfForecastAssumptions
    equity_bridge: DcfEquityBridgeInputs
    starting_basis: DcfStartingBasis | None = None
    normalization_adjustments: tuple[DcfValue, ...] = ()
    model_type: Literal["enterprise_fcff"] = "enterprise_fcff"


def _round(value: float) -> float:
    return round(value, 2)


def _assert_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")


def _required_value(input_value: DcfValue) -> float:
    if input_value.value is None:
        raise ValueError(f"{input_value.name} is required for DCF calculation.")
    if input_value.status in {"unavailable", "invalid"}:
        raise ValueError(
            f"{input_value.name} must be reported, calculated, suggested, "
            "normalized, estimated with warning, or user overridden."
        )
    _assert_finite(input_value.name, input_value.value)
    return input_value.value


def _validate_ratio(
    input_value: DcfValue,
    *,
    minimum: float,
    maximum: float,
    label: str,
) -> float:
    value = _required_value(input_value)
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum:.0%} and {maximum:.0%}.")
    return value


def _validate_currency(inputs: NormalizedDcfInputs) -> None:
    monetary_values = [
        inputs.base_revenue,
        *inputs.normalization_adjustments,
        inputs.equity_bridge.cash_and_equivalents,
        inputs.equity_bridge.total_debt,
        inputs.equity_bridge.marketable_securities,
        inputs.equity_bridge.non_operating_assets,
        inputs.equity_bridge.preferred_stock,
        inputs.equity_bridge.minority_interest,
        inputs.equity_bridge.other_claims,
    ]
    for input_value in monetary_values:
        if input_value is None or input_value.value is None:
            continue
        if input_value.currency and input_value.currency != inputs.currency:
            raise ValueError(
                f"{input_value.name} currency {input_value.currency} does not "
                f"match model currency {inputs.currency}."
            )


def validate_assumptions(assumptions: DcfAssumptions) -> None:
    if not -0.5 <= assumptions.revenue_growth_rate <= 0.5:
        raise ValueError("Revenue growth rate must be between -50% and 50%.")
    if not 0 <= assumptions.free_cash_flow_margin <= 0.8:
        raise ValueError("Free cash flow margin must be between 0% and 80%.")
    if not 0.01 <= assumptions.discount_rate <= 0.5:
        raise ValueError("Discount rate must be between 1% and 50%.")
    if not -0.05 <= assumptions.terminal_growth_rate <= 0.06:
        raise ValueError("Terminal growth rate must be between -5% and 6%.")
    if assumptions.terminal_growth_rate >= assumptions.discount_rate:
        raise ValueError("Terminal growth rate must be lower than discount rate.")
    if not 1 <= assumptions.forecast_years <= 10:
        raise ValueError("Forecast period must be between 1 and 10 years.")


def validate_normalized_inputs(inputs: NormalizedDcfInputs) -> None:
    _validate_currency(inputs)
    assumptions = inputs.assumptions
    if not 1 <= assumptions.forecast_years <= 10:
        raise ValueError("Forecast period must be between 1 and 10 years.")
    if len(assumptions.revenue_growth_rates) != assumptions.forecast_years:
        raise ValueError(
            "Revenue growth path must include one value for each forecast year."
        )
    _validate_yearly_path_length(
        assumptions.ebit_margin_by_year,
        assumptions.forecast_years,
        "EBIT margin path",
    )
    _validate_yearly_path_length(
        assumptions.tax_rate_by_year,
        assumptions.forecast_years,
        "Tax rate path",
    )
    _validate_yearly_path_length(
        assumptions.depreciation_amortization_percent_of_revenue_by_year,
        assumptions.forecast_years,
        "D&A percent of revenue path",
    )
    _validate_yearly_path_length(
        assumptions.capital_expenditure_percent_of_revenue_by_year,
        assumptions.forecast_years,
        "CapEx percent of revenue path",
    )
    _validate_yearly_path_length(
        assumptions.change_in_nwc_percent_of_revenue_by_year,
        assumptions.forecast_years,
        "Change in NWC percent of revenue path",
    )
    _validate_yearly_path_length(
        assumptions.sales_to_capital_by_year,
        assumptions.forecast_years,
        "Sales-to-capital path",
    )
    _validate_yearly_path_length(
        assumptions.roic_by_year,
        assumptions.forecast_years,
        "ROIC path",
    )
    _validate_yearly_path_length(
        assumptions.stock_based_compensation_percent_of_revenue_by_year,
        assumptions.forecast_years,
        "SBC percent of revenue path",
    )
    _validate_yearly_path_length(
        assumptions.share_dilution_rate_by_year,
        assumptions.forecast_years,
        "Share dilution path",
    )

    base_revenue = _required_value(inputs.base_revenue)
    if base_revenue <= 0:
        raise ValueError("Base revenue must be positive.")

    for index, growth in enumerate(assumptions.revenue_growth_rates, start=1):
        _validate_ratio(
            growth,
            minimum=-0.5,
            maximum=0.5,
            label=f"Revenue growth rate for year {index}",
        )
    _validate_ratio(
        assumptions.ebit_margin,
        minimum=-0.8,
        maximum=0.8,
        label="EBIT margin",
    )
    for index, value in enumerate(assumptions.ebit_margin_by_year, start=1):
        _validate_ratio(
            value,
            minimum=-0.8,
            maximum=0.8,
            label=f"EBIT margin for year {index}",
        )
    _validate_ratio(
        assumptions.tax_rate,
        minimum=0,
        maximum=0.6,
        label="Tax rate",
    )
    for index, value in enumerate(assumptions.tax_rate_by_year, start=1):
        _validate_ratio(
            value,
            minimum=0,
            maximum=0.6,
            label=f"Tax rate for year {index}",
        )
    _validate_ratio(
        assumptions.depreciation_amortization_percent_of_revenue,
        minimum=0,
        maximum=0.8,
        label="D&A percent of revenue",
    )
    for index, value in enumerate(
        assumptions.depreciation_amortization_percent_of_revenue_by_year,
        start=1,
    ):
        _validate_ratio(
            value,
            minimum=0,
            maximum=0.8,
            label=f"D&A percent of revenue for year {index}",
        )
    _validate_ratio(
        assumptions.capital_expenditure_percent_of_revenue,
        minimum=0,
        maximum=0.8,
        label="CapEx percent of revenue",
    )
    for index, value in enumerate(
        assumptions.capital_expenditure_percent_of_revenue_by_year,
        start=1,
    ):
        _validate_ratio(
            value,
            minimum=0,
            maximum=0.8,
            label=f"CapEx percent of revenue for year {index}",
        )
    _validate_ratio(
        assumptions.change_in_nwc_percent_of_revenue,
        minimum=-0.5,
        maximum=0.5,
        label="Change in NWC percent of revenue",
    )
    for index, value in enumerate(
        assumptions.change_in_nwc_percent_of_revenue_by_year,
        start=1,
    ):
        _validate_ratio(
            value,
            minimum=-0.5,
            maximum=0.5,
            label=f"Change in NWC percent of revenue for year {index}",
        )
    if assumptions.reinvestment_method == "sales_to_capital":
        if not assumptions.sales_to_capital_by_year:
            raise ValueError(
                "Sales-to-capital reinvestment requires one sales-to-capital value for each forecast year."
            )
        for index, value in enumerate(assumptions.sales_to_capital_by_year, start=1):
            sales_to_capital = _required_value(value)
            if not 0.1 <= sales_to_capital <= 20:
                raise ValueError(
                    f"Sales-to-capital for year {index} must be between 0.1x and 20.0x."
                )
    if assumptions.reinvestment_method == "roic_based":
        if not assumptions.roic_by_year:
            raise ValueError(
                "ROIC-based reinvestment requires one ROIC value for each forecast year."
            )
        for index, value in enumerate(assumptions.roic_by_year, start=1):
            _validate_ratio(
                value,
                minimum=0.01,
                maximum=1.5,
                label=f"ROIC for year {index}",
            )
    for index, value in enumerate(
        assumptions.stock_based_compensation_percent_of_revenue_by_year,
        start=1,
    ):
        _validate_ratio(
            value,
            minimum=0,
            maximum=0.5,
            label=f"SBC percent of revenue for year {index}",
        )
    for index, value in enumerate(assumptions.share_dilution_rate_by_year, start=1):
        _validate_ratio(
            value,
            minimum=-0.25,
            maximum=0.5,
            label=f"Share dilution rate for year {index}",
        )
    wacc = _validate_ratio(
        assumptions.wacc,
        minimum=0.01,
        maximum=0.5,
        label="WACC",
    )
    terminal_growth = _validate_ratio(
        assumptions.terminal_growth_rate,
        minimum=-0.05,
        maximum=0.06,
        label="Terminal growth rate",
    )
    if terminal_growth >= wacc:
        raise ValueError("Terminal growth rate must be lower than WACC.")
    if wacc - terminal_growth < assumptions.terminal_value_min_spread:
        raise ValueError(
            "WACC minus terminal growth must be at least "
            f"{assumptions.terminal_value_min_spread:.1%}."
        )

    cash = _required_value(inputs.equity_bridge.cash_and_equivalents)
    debt = _required_value(inputs.equity_bridge.total_debt)
    shares = _required_value(inputs.equity_bridge.diluted_shares)
    if cash < 0:
        raise ValueError("Cash and equivalents cannot be negative.")
    if debt < 0:
        raise ValueError("Total debt cannot be negative.")
    if shares <= 0:
        raise ValueError("Diluted shares must be positive.")
    if inputs.starting_basis is not None:
        _validate_starting_basis(inputs)


def _validate_starting_basis(inputs: NormalizedDcfInputs) -> None:
    basis = inputs.starting_basis
    if basis is None:
        return
    if basis.basis_type == "latest_ttm":
        if basis.calculation_method not in {
            "annual_plus_current_ytd_minus_prior_ytd",
            "four_validated_standalone_quarters",
        }:
            raise ValueError("Latest TTM starting basis requires a valid TTM method.")
        if not basis.period_start or not basis.period_end:
            raise ValueError("Latest TTM starting basis requires period dates.")
        if (
            inputs.base_revenue.lineage.period_end
            and inputs.base_revenue.lineage.period_end != basis.period_end
        ):
            raise ValueError(
                "Base revenue period end must match the selected TTM period end."
            )
    if basis.basis_type == "latest_fiscal_year" and not basis.period_end:
        raise ValueError("Latest fiscal year starting basis requires period end.")
    if basis.basis_type == "normalized" and not basis.calculation_method:
        raise ValueError("Normalized starting basis requires a calculation method.")


def _validate_yearly_path_length(
    values: tuple[DcfValue, ...],
    forecast_years: int,
    label: str,
) -> None:
    if values and len(values) != forecast_years:
        raise ValueError(f"{label} must include one value for each forecast year.")


def _yearly_input(
    values: tuple[DcfValue, ...],
    fallback: DcfValue,
    year_index: int,
) -> DcfValue:
    if values:
        return values[year_index]
    return fallback


def _forecast_row_basis(method: ReinvestmentMethod) -> str:
    if method == "sales_to_capital":
        return (
            "FCFF = NOPAT - reinvestment; reinvestment = change in revenue / "
            "sales-to-capital. Direct D&A, CapEx, and NWC rows are shown as "
            "non-controlling operating evidence."
        )
    if method == "roic_based":
        return (
            "FCFF = NOPAT - reinvestment; reinvestment rate = revenue growth / "
            "ROIC, and reinvestment = NOPAT x reinvestment rate. Direct D&A, "
            "CapEx, and NWC rows are shown as non-controlling operating evidence."
        )
    return "FCFF = NOPAT + D&A - CapEx - change in NWC."


def calculate_normalized_dcf(inputs: NormalizedDcfInputs) -> dict:
    validate_normalized_inputs(inputs)

    assumptions = inputs.assumptions
    reported_base_revenue = _required_value(inputs.base_revenue)
    normalization_adjustment_total = sum(
        _required_value(adjustment) for adjustment in inputs.normalization_adjustments
    )
    base_revenue = reported_base_revenue + normalization_adjustment_total
    if base_revenue <= 0:
        raise ValueError("Base revenue plus normalization adjustments must be positive.")
    wacc = _required_value(assumptions.wacc)
    terminal_wacc = _required_value(assumptions.terminal_wacc) if assumptions.terminal_wacc else wacc
    terminal_growth = _required_value(assumptions.terminal_growth_rate)
    projected_shares = _required_value(inputs.equity_bridge.diluted_shares)

    projected_cash_flows = []
    present_value_sum = 0.0
    revenue = base_revenue
    final_fcff = 0.0

    for year, growth_input in enumerate(assumptions.revenue_growth_rates, start=1):
        year_index = year - 1
        growth = _required_value(growth_input)
        prior_revenue = revenue
        ebit_margin_input = _yearly_input(
            assumptions.ebit_margin_by_year,
            assumptions.ebit_margin,
            year_index,
        )
        tax_rate_input = _yearly_input(
            assumptions.tax_rate_by_year,
            assumptions.tax_rate,
            year_index,
        )
        da_percent_input = _yearly_input(
            assumptions.depreciation_amortization_percent_of_revenue_by_year,
            assumptions.depreciation_amortization_percent_of_revenue,
            year_index,
        )
        capex_percent_input = _yearly_input(
            assumptions.capital_expenditure_percent_of_revenue_by_year,
            assumptions.capital_expenditure_percent_of_revenue,
            year_index,
        )
        nwc_percent_input = _yearly_input(
            assumptions.change_in_nwc_percent_of_revenue_by_year,
            assumptions.change_in_nwc_percent_of_revenue,
            year_index,
        )
        ebit_margin = _required_value(ebit_margin_input)
        tax_rate = _required_value(tax_rate_input)
        da_percent = _required_value(da_percent_input)
        capex_percent = _required_value(capex_percent_input)
        nwc_percent = _required_value(nwc_percent_input)
        revenue *= 1 + growth
        ebit = revenue * ebit_margin
        nopat = ebit * (1 - tax_rate)
        depreciation_amortization = revenue * da_percent
        capital_expenditure = revenue * capex_percent
        change_in_nwc = revenue * nwc_percent
        sbc_input = (
            assumptions.stock_based_compensation_percent_of_revenue_by_year[year_index]
            if assumptions.stock_based_compensation_percent_of_revenue_by_year
            else None
        )
        share_dilution_input = (
            assumptions.share_dilution_rate_by_year[year_index]
            if assumptions.share_dilution_rate_by_year
            else None
        )
        sbc = revenue * _required_value(sbc_input) if sbc_input else 0.0
        if share_dilution_input:
            projected_shares *= 1 + _required_value(share_dilution_input)
        direct_reinvestment = (
            capital_expenditure + change_in_nwc - depreciation_amortization
        )
        reinvestment = direct_reinvestment
        reinvestment_rate = None
        active_reinvestment_input_name = "direct_fcff_driver_rows"
        if assumptions.reinvestment_method == "sales_to_capital":
            sales_to_capital_input = assumptions.sales_to_capital_by_year[year_index]
            sales_to_capital = _required_value(sales_to_capital_input)
            reinvestment = (revenue - prior_revenue) / sales_to_capital
            active_reinvestment_input_name = sales_to_capital_input.name
        elif assumptions.reinvestment_method == "roic_based":
            roic_input = assumptions.roic_by_year[year_index]
            roic = _required_value(roic_input)
            reinvestment_rate = growth / roic
            reinvestment = nopat * reinvestment_rate
            active_reinvestment_input_name = roic_input.name
        fcff = nopat - reinvestment + sbc
        discount_divisor = (1 + wacc) ** year
        discount_factor = 1 / discount_divisor
        present_value = fcff * discount_factor
        final_fcff = fcff
        present_value_sum += present_value
        projected_cash_flows.append(
            {
                "year": year,
                "revenue": _round(revenue),
                "revenue_growth_rate": growth,
                "ebit": _round(ebit),
                "tax_rate": tax_rate,
                "nopat": _round(nopat),
                "depreciation_amortization": _round(depreciation_amortization),
                "capital_expenditure": _round(capital_expenditure),
                "change_in_net_working_capital": _round(change_in_nwc),
                "free_cash_flow": _round(fcff),
                "fcff": _round(fcff),
                "reinvestment": _round(reinvestment),
                "direct_driver_reinvestment": _round(direct_reinvestment),
                "stock_based_compensation": _round(sbc),
                "diluted_shares": _round(projected_shares),
                "reinvestment_rate": (
                    round(reinvestment_rate, 6)
                    if reinvestment_rate is not None
                    else None
                ),
                "reinvestment_method": assumptions.reinvestment_method,
                "discount_factor": round(discount_factor, 6),
                "present_value": _round(present_value),
                "basis": _forecast_row_basis(assumptions.reinvestment_method),
                "discount_basis": (
                    "Present value = FCFF x standard discount factor. "
                    "Discount factor = 1 / (1 + WACC) ^ year."
                ),
                "source_inputs": [
                    inputs.base_revenue.name,
                    growth_input.name,
                    ebit_margin_input.name,
                    tax_rate_input.name,
                    da_percent_input.name,
                    capex_percent_input.name,
                    nwc_percent_input.name,
                    active_reinvestment_input_name,
                    sbc_input.name if sbc_input else "sbc_not_added_back",
                    share_dilution_input.name if share_dilution_input else "no_share_dilution_path",
                    assumptions.wacc.name,
                ],
            }
        )

    terminal_fcff = final_fcff * (1 + terminal_growth)
    terminal_value = terminal_fcff / (terminal_wacc - terminal_growth)
    terminal_discount_divisor = (1 + wacc) ** assumptions.forecast_years
    terminal_discount_factor = 1 / terminal_discount_divisor
    terminal_present_value = terminal_value * terminal_discount_factor
    enterprise_value = present_value_sum + terminal_present_value

    equity_bridge = _calculate_equity_bridge(inputs.equity_bridge, enterprise_value)
    fair_value_per_share = equity_bridge["equity_value"] / projected_shares

    warnings = _valuation_warnings(
        enterprise_value=enterprise_value,
        terminal_present_value=terminal_present_value,
        terminal_growth=terminal_growth,
        wacc=terminal_wacc,
        projected_cash_flows=projected_cash_flows,
    )

    return {
        "model_type": inputs.model_type,
        "currency": inputs.currency,
        "status": "calculated",
        "projected_cash_flows": projected_cash_flows,
        "terminal_value": {
            "value": _round(terminal_value),
            "present_value": _round(terminal_present_value),
            "terminal_year_revenue": _round(revenue * (1 + terminal_growth)),
            "terminal_year_ebit": _round(ebit * (1 + terminal_growth)),
            "terminal_year_nopat": _round(nopat * (1 + terminal_growth)),
            "terminal_year_reinvestment": _round(reinvestment * (1 + terminal_growth)),
            "terminal_year_fcff": _round(final_fcff),
            "terminal_fcff": _round(terminal_fcff),
            "terminal_growth_rate": terminal_growth,
            "wacc": terminal_wacc,
            "wacc_terminal_growth_spread": round(terminal_wacc - terminal_growth, 6),
            "discount_factor_to_present": round(terminal_discount_factor, 6),
            "percent_of_enterprise_value": (
                round(terminal_present_value / enterprise_value, 6)
                if enterprise_value
                else None
            ),
            "method": "gordon_growth",
            "basis": (
                "Terminal value = terminal FCFF / (Terminal WACC - terminal growth), "
                "where terminal FCFF = final forecast year FCFF x (1 + terminal growth)."
            ),
            "source_inputs": [
                "final_forecast_year_fcff",
                assumptions.terminal_wacc.name if assumptions.terminal_wacc else assumptions.wacc.name,
                assumptions.terminal_growth_rate.name,
            ],
        },
        "enterprise_value": {
            "value": _round(enterprise_value),
            "explicit_forecast_present_value": _round(present_value_sum),
            "terminal_present_value": _round(terminal_present_value),
            "explicit_forecast_percent_of_enterprise_value": (
                round(present_value_sum / enterprise_value, 6)
                if enterprise_value
                else None
            ),
            "terminal_value_percent_of_enterprise_value": (
                round(terminal_present_value / enterprise_value, 6)
                if enterprise_value
                else None
            ),
            "basis": (
                "Present value of explicit forecast FCFF plus present value "
                "of terminal value."
            ),
        },
        "equity_bridge": equity_bridge,
        "equity_value": _round(equity_bridge["equity_value"]),
        "fair_value_per_share": _round(fair_value_per_share),
        "normalized_inputs": {
            "starting_basis": (
                inputs.starting_basis.to_dict()
                if inputs.starting_basis
                else _legacy_annual_starting_basis(inputs).to_dict()
            ),
            "base_revenue": inputs.base_revenue.to_dict(),
            "normalization_adjustments": [
                adjustment.to_dict()
                for adjustment in inputs.normalization_adjustments
            ],
            "effective_base_revenue": {
                "value": _round(base_revenue),
                "reported_base_revenue": _round(reported_base_revenue),
                "normalization_adjustment_total": _round(normalization_adjustment_total),
                "basis": "Reported starting revenue plus explicit user-reviewed normalization adjustments.",
            },
            "assumptions": _assumptions_to_dict(assumptions),
            "equity_bridge": _equity_bridge_inputs_to_dict(inputs.equity_bridge),
        },
        "data_quality": _dcf_data_quality(inputs),
        "warnings": warnings,
        "calculation_basis": (
            "Enterprise-value FCFF DCF. Reported, calculated, suggested, and "
            "user-overridden inputs retain lineage and are validated before "
            "any valuation output is calculated."
        ),
    }


def _calculate_equity_bridge(
    bridge: DcfEquityBridgeInputs,
    enterprise_value: float,
) -> dict:
    rows = [
        {
            "label": "Enterprise Value",
            "operation": "start",
            "value": _round(enterprise_value),
            "basis": "DCF enterprise value.",
            "source_input": None,
        }
    ]
    equity_value = enterprise_value

    for label, operation, input_value in (
        ("Cash and Equivalents", "add", bridge.cash_and_equivalents),
        ("Marketable Securities", "add", bridge.marketable_securities),
        ("Non-operating Assets", "add", bridge.non_operating_assets),
        ("Total Debt", "subtract", bridge.total_debt),
        ("Preferred Stock", "subtract", bridge.preferred_stock),
        ("Minority Interest", "subtract", bridge.minority_interest),
        ("Other Claims", "subtract", bridge.other_claims),
    ):
        if input_value is None:
            continue
        value = _required_value(input_value)
        if operation == "add":
            equity_value += value
        else:
            equity_value -= value
        rows.append(
            {
                "label": label,
                "operation": operation,
                "value": _round(value),
                "basis": input_value.basis,
                "source_input": input_value.to_dict(),
            }
        )

    shares = _required_value(bridge.diluted_shares)
    rows.extend(
        [
            {
                "label": "Equity Value",
                "operation": "equals",
                "value": _round(equity_value),
                "basis": "Enterprise value adjusted for supplied bridge items.",
                "source_input": None,
            },
            {
                "label": "Diluted Shares",
                "operation": "divide",
                "value": _round(shares),
                "basis": bridge.diluted_shares.basis,
                "source_input": bridge.diluted_shares.to_dict(),
            },
            {
                "label": "Fair Value Per Share",
                "operation": "equals",
                "value": _round(equity_value / shares),
                "basis": "Equity value divided by diluted shares.",
                "source_input": None,
            },
        ]
    )
    return {
        "rows": rows,
        "equity_value": equity_value,
        "basis": "Equity value = enterprise value plus cash/assets minus debt/claims.",
    }


def _valuation_warnings(
    *,
    enterprise_value: float,
    terminal_present_value: float,
    terminal_growth: float,
    wacc: float,
    projected_cash_flows: list[dict],
) -> list[str]:
    warnings = []
    if enterprise_value > 0 and terminal_present_value / enterprise_value > 0.75:
        warnings.append(
            "Terminal value is more than 75% of enterprise value; review long-term assumptions."
        )
    if terminal_growth > 0.04:
        warnings.append("Terminal growth rate is above 4%; review sustainability.")
    if wacc - terminal_growth < 0.01:
        warnings.append("WACC minus terminal growth spread is narrow.")
    negative_reinvestment_growth_years = [
        row["year"]
        for row in projected_cash_flows
        if row.get("revenue_growth_rate", 0) > 0 and row.get("reinvestment", 0) < 0
    ]
    if negative_reinvestment_growth_years:
        warnings.append(
            "Revenue continues to grow while net reinvestment is negative in "
            f"year(s) {', '.join(str(year) for year in negative_reinvestment_growth_years)}. "
            "Review CapEx, D&A, and working-capital assumptions."
        )
    capex_below_da_years = [
        row["year"]
        for row in projected_cash_flows
        if row.get("capital_expenditure", 0) < row.get("depreciation_amortization", 0)
    ]
    if len(capex_below_da_years) >= 2:
        warnings.append(
            "CapEx remains below D&A for multiple forecast years; review whether "
            "asset reinvestment is sufficient for the growth path."
        )
    final_row = projected_cash_flows[-1] if projected_cash_flows else {}
    if terminal_growth > 0 and final_row.get("reinvestment", 0) <= 0:
        warnings.append(
            "Terminal growth is positive while terminal-year net reinvestment is "
            "non-positive. Review terminal economics before relying on the valuation."
        )
    return warnings


def _assumptions_to_dict(assumptions: DcfForecastAssumptions) -> dict:
    return {
        "forecast_years": assumptions.forecast_years,
        "revenue_growth_rates": [
            input_value.to_dict()
            for input_value in assumptions.revenue_growth_rates
        ],
        "ebit_margin": assumptions.ebit_margin.to_dict(),
        "tax_rate": assumptions.tax_rate.to_dict(),
        "depreciation_amortization_percent_of_revenue": (
            assumptions.depreciation_amortization_percent_of_revenue.to_dict()
        ),
        "capital_expenditure_percent_of_revenue": (
            assumptions.capital_expenditure_percent_of_revenue.to_dict()
        ),
        "change_in_nwc_percent_of_revenue": (
            assumptions.change_in_nwc_percent_of_revenue.to_dict()
        ),
        "wacc": assumptions.wacc.to_dict(),
        "terminal_growth_rate": assumptions.terminal_growth_rate.to_dict(),
        "terminal_value_min_spread": assumptions.terminal_value_min_spread,
        "ebit_margin_by_year": [
            input_value.to_dict() for input_value in assumptions.ebit_margin_by_year
        ],
        "tax_rate_by_year": [
            input_value.to_dict() for input_value in assumptions.tax_rate_by_year
        ],
        "depreciation_amortization_percent_of_revenue_by_year": [
            input_value.to_dict()
            for input_value in (
                assumptions.depreciation_amortization_percent_of_revenue_by_year
            )
        ],
        "capital_expenditure_percent_of_revenue_by_year": [
            input_value.to_dict()
            for input_value in assumptions.capital_expenditure_percent_of_revenue_by_year
        ],
        "change_in_nwc_percent_of_revenue_by_year": [
            input_value.to_dict()
            for input_value in assumptions.change_in_nwc_percent_of_revenue_by_year
        ],
        "reinvestment_method": assumptions.reinvestment_method,
        "sales_to_capital_by_year": [
            input_value.to_dict()
            for input_value in assumptions.sales_to_capital_by_year
        ],
        "roic_by_year": [
            input_value.to_dict()
            for input_value in assumptions.roic_by_year
        ],
        "stock_based_compensation_percent_of_revenue_by_year": [
            input_value.to_dict()
            for input_value in assumptions.stock_based_compensation_percent_of_revenue_by_year
        ],
        "share_dilution_rate_by_year": [
            input_value.to_dict()
            for input_value in assumptions.share_dilution_rate_by_year
        ],
    }


def _equity_bridge_inputs_to_dict(bridge: DcfEquityBridgeInputs) -> dict:
    return {
        "cash_and_equivalents": bridge.cash_and_equivalents.to_dict(),
        "total_debt": bridge.total_debt.to_dict(),
        "diluted_shares": bridge.diluted_shares.to_dict(),
        "marketable_securities": (
            bridge.marketable_securities.to_dict()
            if bridge.marketable_securities
            else None
        ),
        "non_operating_assets": (
            bridge.non_operating_assets.to_dict()
            if bridge.non_operating_assets
            else None
        ),
        "preferred_stock": (
            bridge.preferred_stock.to_dict() if bridge.preferred_stock else None
        ),
        "minority_interest": (
            bridge.minority_interest.to_dict()
            if bridge.minority_interest
            else None
        ),
        "other_claims": (
            bridge.other_claims.to_dict() if bridge.other_claims else None
        ),
    }


def _legacy_annual_starting_basis(inputs: NormalizedDcfInputs) -> DcfStartingBasis:
    period_end = inputs.base_revenue.lineage.period_end
    return DcfStartingBasis(
        basis_type="latest_fiscal_year",
        selected_by="system",
        period_start=inputs.base_revenue.lineage.period_start,
        period_end=period_end,
        calculation_method="legacy_contract_without_explicit_starting_basis",
        data_quality="low",
        reason_codes=("TTM_FALLBACK_ANNUAL", "LEGACY_CONTRACT"),
        warnings=(
            "No explicit starting basis was supplied; preserving annual-style legacy behavior.",
        ),
    )


def _dcf_data_quality(inputs: NormalizedDcfInputs) -> dict:
    basis = inputs.starting_basis or _legacy_annual_starting_basis(inputs)
    required_inputs = [
        inputs.base_revenue,
        inputs.assumptions.ebit_margin,
        inputs.assumptions.tax_rate,
        inputs.assumptions.depreciation_amortization_percent_of_revenue,
        inputs.assumptions.capital_expenditure_percent_of_revenue,
        inputs.assumptions.change_in_nwc_percent_of_revenue,
        inputs.assumptions.wacc,
        inputs.assumptions.terminal_growth_rate,
        inputs.equity_bridge.cash_and_equivalents,
        inputs.equity_bridge.total_debt,
        inputs.equity_bridge.diluted_shares,
    ]
    overrides = sum(1 for value in required_inputs if value.user_overridden)
    unavailable = sum(
        1 for value in required_inputs if value.status in {"unavailable", "invalid"}
    )
    reason_codes = list(basis.reason_codes)
    if basis.basis_type == "latest_ttm":
        reason_codes.append("TTM_COMPLETE")
    elif basis.basis_type == "latest_fiscal_year":
        reason_codes.append("TTM_FALLBACK_ANNUAL")
    else:
        reason_codes.append("NORMALIZED_STARTING_BASIS")
    if overrides:
        reason_codes.append("USER_OVERRIDES_PRESENT")
    if unavailable:
        reason_codes.append("MISSING_REQUIRED_INPUT")

    if unavailable:
        label = "insufficient"
    elif basis.data_quality == "high" and overrides <= 2:
        label = "high"
    elif basis.data_quality in {"high", "medium"}:
        label = "medium"
    else:
        label = "low"
    return {
        "label": label,
        "basis_quality": basis.data_quality,
        "reason_codes": sorted(set(reason_codes)),
        "user_override_count": overrides,
        "unavailable_required_input_count": unavailable,
    }


def _legacy_value(name: str, value: float, unit: str, currency: str | None) -> DcfValue:
    return DcfValue(
        name=name,
        value=value,
        status="user_override",
        unit=unit,
        currency=currency,
        basis="User-provided value from the legacy DCF request contract.",
        user_overridden=True,
        confidence="low",
    )


def _calculate_legacy_dcf(inputs: DcfInputs) -> dict:
    validate_assumptions(inputs.assumptions)

    if inputs.base_revenue <= 0:
        raise ValueError("Base revenue must be positive.")
    if inputs.cash_and_equivalents < 0:
        raise ValueError("Cash and equivalents cannot be negative.")
    if inputs.total_debt < 0:
        raise ValueError("Total debt cannot be negative.")
    if inputs.shares_outstanding <= 0:
        raise ValueError("Shares outstanding must be positive.")

    assumptions = inputs.assumptions
    projected_cash_flows = []
    present_value_sum = 0.0

    for year in range(1, assumptions.forecast_years + 1):
        revenue = inputs.base_revenue * ((1 + assumptions.revenue_growth_rate) ** year)
        cash_flow = revenue * assumptions.free_cash_flow_margin
        discount_factor = (1 + assumptions.discount_rate) ** year
        present_value = cash_flow / discount_factor
        present_value_sum += present_value
        projected_cash_flows.append(
            {
                "year": year,
                "revenue": _round(revenue),
                "free_cash_flow": _round(cash_flow),
                "present_value": _round(present_value),
            }
        )

    final_cash_flow = projected_cash_flows[-1]["free_cash_flow"]
    terminal_value = final_cash_flow * (1 + assumptions.terminal_growth_rate)
    terminal_value /= assumptions.discount_rate - assumptions.terminal_growth_rate
    terminal_present_value = terminal_value / (
        (1 + assumptions.discount_rate) ** assumptions.forecast_years
    )

    enterprise_value = present_value_sum + terminal_present_value
    equity_value = enterprise_value + inputs.cash_and_equivalents - inputs.total_debt
    fair_value_per_share = equity_value / inputs.shares_outstanding

    return {
        "projected_cash_flows": projected_cash_flows,
        "terminal_value": _round(terminal_value),
        "terminal_present_value": _round(terminal_present_value),
        "enterprise_value": _round(enterprise_value),
        "equity_value": _round(equity_value),
        "fair_value_per_share": _round(fair_value_per_share),
        "assumptions": {
            "revenue_growth_rate": assumptions.revenue_growth_rate,
            "free_cash_flow_margin": assumptions.free_cash_flow_margin,
            "discount_rate": assumptions.discount_rate,
            "terminal_growth_rate": assumptions.terminal_growth_rate,
            "forecast_years": assumptions.forecast_years,
        },
        "normalized_inputs": _legacy_normalized_input_summary(inputs),
        "warnings": [
            "Legacy simplified DCF uses a user-provided free-cash-flow margin rather than FCFF driver rows."
        ],
        "calculation_basis": (
            "Projected revenue multiplied by user-provided free cash flow margin, "
            "discounted annually, plus Gordon growth terminal value."
        ),
    }


def _legacy_normalized_input_summary(inputs: DcfInputs) -> dict:
    currency = "USD"
    return {
        "base_revenue": _legacy_value(
            "base_revenue",
            inputs.base_revenue,
            "currency",
            currency,
        ).to_dict(),
        "assumptions": {
            "revenue_growth_rate": _legacy_value(
                "revenue_growth_rate",
                inputs.assumptions.revenue_growth_rate,
                "ratio",
                None,
            ).to_dict(),
            "free_cash_flow_margin": _legacy_value(
                "free_cash_flow_margin",
                inputs.assumptions.free_cash_flow_margin,
                "ratio",
                None,
            ).to_dict(),
            "discount_rate": _legacy_value(
                "discount_rate",
                inputs.assumptions.discount_rate,
                "ratio",
                None,
            ).to_dict(),
            "terminal_growth_rate": _legacy_value(
                "terminal_growth_rate",
                inputs.assumptions.terminal_growth_rate,
                "ratio",
                None,
            ).to_dict(),
            "forecast_years": inputs.assumptions.forecast_years,
        },
        "equity_bridge": {
            "cash_and_equivalents": _legacy_value(
                "cash_and_equivalents",
                inputs.cash_and_equivalents,
                "currency",
                currency,
            ).to_dict(),
            "total_debt": _legacy_value(
                "total_debt",
                inputs.total_debt,
                "currency",
                currency,
            ).to_dict(),
            "shares_outstanding": _legacy_value(
                "shares_outstanding",
                inputs.shares_outstanding,
                "shares",
                None,
            ).to_dict(),
        },
    }


def calculate_dcf(inputs: DcfInputs | NormalizedDcfInputs) -> dict:
    if isinstance(inputs, NormalizedDcfInputs):
        return calculate_normalized_dcf(inputs)
    return _calculate_legacy_dcf(inputs)
