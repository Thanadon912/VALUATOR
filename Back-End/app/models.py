from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.validation import normalize_ticker


class DcfAssumptionsRequest(BaseModel):
    revenue_growth_rate: float = Field(ge=-0.5, le=0.5)
    free_cash_flow_margin: float = Field(ge=0, le=0.8)
    discount_rate: float = Field(ge=0.01, le=0.5)
    terminal_growth_rate: float = Field(ge=-0.05, le=0.06)
    forecast_years: int = Field(ge=1, le=10)


class DcfRequest(BaseModel):
    ticker: str
    base_revenue: float = Field(gt=0)
    cash_and_equivalents: float = Field(ge=0)
    total_debt: float = Field(ge=0)
    shares_outstanding: float = Field(gt=0)
    assumptions: DcfAssumptionsRequest

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        return normalize_ticker(value)


class CompanyProfileInternational(BaseModel):
    """International terms required to normalize a US-listed security."""
    reported_currency: str | None = None
    country_of_domicile: str | None = None
    is_foreign_private_issuer: bool = False
    adr_ratio: float = Field(default=1.0, gt=0)
    adr_ratio_source: str | None = None


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


class DcfSourceLineageRequest(BaseModel):
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


class DcfInputValueRequest(BaseModel):
    value: float | None = None
    status: DcfValueStatus
    unit: str | None = None
    currency: str | None = None
    basis: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    lineage: DcfSourceLineageRequest = Field(
        default_factory=DcfSourceLineageRequest
    )
    confidence: Literal["high", "medium", "low", "insufficient"] | None = None
    warnings: list[str] = Field(default_factory=list)
    user_overridden: bool = False


class DcfForecastAssumptionsRequest(BaseModel):
    forecast_years: int = Field(ge=1, le=10)
    revenue_growth_rates: list[DcfInputValueRequest]
    ebit_margin: DcfInputValueRequest
    tax_rate: DcfInputValueRequest
    depreciation_amortization_percent_of_revenue: DcfInputValueRequest
    capital_expenditure_percent_of_revenue: DcfInputValueRequest
    change_in_nwc_percent_of_revenue: DcfInputValueRequest
    wacc: DcfInputValueRequest
    terminal_growth_rate: DcfInputValueRequest
    terminal_wacc: DcfInputValueRequest | None = None
    terminal_value_min_spread: float = Field(default=0.005, ge=0.001, le=0.05)
    ebit_margin_by_year: list[DcfInputValueRequest] = Field(default_factory=list)
    tax_rate_by_year: list[DcfInputValueRequest] = Field(default_factory=list)
    depreciation_amortization_percent_of_revenue_by_year: list[
        DcfInputValueRequest
    ] = Field(default_factory=list)
    capital_expenditure_percent_of_revenue_by_year: list[
        DcfInputValueRequest
    ] = Field(default_factory=list)
    change_in_nwc_percent_of_revenue_by_year: list[
        DcfInputValueRequest
    ] = Field(default_factory=list)
    reinvestment_method: Literal[
        "direct_fcff_drivers",
        "sales_to_capital",
        "roic_based",
    ] = "direct_fcff_drivers"
    sales_to_capital_by_year: list[DcfInputValueRequest] = Field(
        default_factory=list
    )
    roic_by_year: list[DcfInputValueRequest] = Field(default_factory=list)
    stock_based_compensation_percent_of_revenue_by_year: list[
        DcfInputValueRequest
    ] = Field(default_factory=list)
    share_dilution_rate_by_year: list[DcfInputValueRequest] = Field(
        default_factory=list
    )


class DcfEquityBridgeRequest(BaseModel):
    cash_and_equivalents: DcfInputValueRequest
    total_debt: DcfInputValueRequest
    diluted_shares: DcfInputValueRequest
    marketable_securities: DcfInputValueRequest | None = None
    non_operating_assets: DcfInputValueRequest | None = None
    preferred_stock: DcfInputValueRequest | None = None
    minority_interest: DcfInputValueRequest | None = None
    other_claims: DcfInputValueRequest | None = None


class DcfStartingBasisRequest(BaseModel):
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
    source_facts: list[dict[str, Any]] = Field(default_factory=list)
    data_quality: Literal["high", "medium", "low", "insufficient"] = "insufficient"
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    user_overridden: bool = False


class NormalizedDcfRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    starting_basis: DcfStartingBasisRequest | None = None
    base_revenue: DcfInputValueRequest
    assumptions: DcfForecastAssumptionsRequest
    equity_bridge: DcfEquityBridgeRequest
    normalization_adjustments: list[DcfInputValueRequest] = Field(
        default_factory=list
    )
    model_type: Literal["enterprise_fcff"] = "enterprise_fcff"

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class WorkspaceSection(BaseModel):
    status: str
    source: str | None = None
    source_timestamp: str | None = None
    message: str


class WorkspaceResponse(BaseModel):
    ticker: str
    mode: str
    sections: dict[str, WorkspaceSection]
    required_user_inputs: list[str]


ResponseStatus = Literal[
    "success",
    "partial",
    "unavailable",
    "missing_input",
    "stale",
    "error",
]


class SourceRecord(BaseModel):
    provider: str
    source_url: str | None = None
    source_timestamp: str | None = None
    fetched_at: str
    is_stale: bool = False


class AdaptiveFinancialMetric(BaseModel):
    period: str | None = None
    start: str | None = None
    end: str | None = None
    value: float | int | None = None
    unit: str | None = None
    concept: str | None = None
    form: str | None = None
    filed: str | None = None
    accession: str | None = None
    status: str | None = None
    basis: str | None = None
    input_refs: list[str] = Field(default_factory=list)


class AdaptiveValuationData(BaseModel):
    sic_code: str | None = None
    sic_description: str | None = None
    sector: str | None = None
    industry: str | None = None
    revenue_history: list[AdaptiveFinancialMetric] = Field(default_factory=list)
    r_and_d_history: list[AdaptiveFinancialMetric] = Field(default_factory=list)
    net_income_history: list[AdaptiveFinancialMetric] = Field(default_factory=list)
    regulatory_capital: dict[str, AdaptiveFinancialMetric | None] = Field(
        default_factory=dict
    )
    capex_history: list[AdaptiveFinancialMetric] = Field(default_factory=list)
    total_debt: AdaptiveFinancialMetric | None = None
    cash_and_cash_equivalents: AdaptiveFinancialMetric | None = None
    operating_income_history: list[AdaptiveFinancialMetric] = Field(default_factory=list)
    operating_margin_history: list[AdaptiveFinancialMetric] = Field(default_factory=list)


class ValuationInputsResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    adaptive_valuation_data: AdaptiveValuationData = Field(
        default_factory=AdaptiveValuationData
    )
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ValuationMethodologyResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None = None
    methodology: str
    sic_code: str | None = None
    sic_description: str | None = None
    adaptive_valuation_data: AdaptiveValuationData = Field(
        default_factory=AdaptiveValuationData
    )
    warnings: list[str] = Field(default_factory=list)


class ProjectionYear(BaseModel):
    model_config = ConfigDict(extra="allow")

    year: int
    revenue: float | None = None
    revenue_growth: float | None = None
    net_income: float | None = None
    net_income_growth: float | None = None
    capital_deduction_label: str | None = None
    capital_deduction_value: float | None = None
    unlevered_free_cash_flow: float | None = None
    free_cash_flow_to_equity: float | None = None


class ScenarioPayload(BaseModel):
    projections: list[ProjectionYear] = Field(default_factory=list)
    harvest_start_year: int | None = None


class ForwardDCF(BaseModel):
    valuation_status: str
    fair_value: float | None = None
    fcf_growth_rate: float | None = None
    wacc: float | None = None
    projections: list[ProjectionYear] = Field(default_factory=list)
    sensitivity_matrix: list[dict[str, Any]] = Field(default_factory=list)
    scenarios: dict[str, ScenarioPayload] = Field(default_factory=dict)


class ReverseDCFSOTP(BaseModel):
    is_active: bool = False
    solver_available: bool = False
    requested_target_price: float | None = None
    model_fair_value: float | None = None
    target_price: float | None = None
    implied_growth_rate: float | None = None
    total_ev: float | None = None
    net_cash: float | None = None
    years: int | None = None
    horizon_years: int | None = None
    high_growth_segment_name: str | None = None
    classification_profile: str | None = None
    segments: list[dict[str, Any]] = Field(default_factory=list)


class MonteCarloHistogramBin(BaseModel):
    lower_bound: float
    upper_bound: float
    count: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class MonteCarloResults(BaseModel):
    bear_p10: float | None = None
    base_p50: float | None = None
    bull_p90: float | None = None
    iteration_count: int | None = None
    valid_sample_count: int | None = None
    distribution: Literal["normal"] | None = None
    random_seed: int | None = None
    histogram_bins: list[MonteCarloHistogramBin] = Field(default_factory=list)
    live_price_percentile: float | None = Field(default=None, ge=0, le=100)


class ValuationResponse(BaseModel):
    ticker: str
    timestamp: str
    current_price: float | None = None
    computed_fair_value: float | None = None
    valuation_status: str
    margin_of_safety_percentage: float
    valuation_methodology: str
    engine_metadata: dict[str, Any] = Field(default_factory=dict)
    projections: list[ProjectionYear] = Field(default_factory=list)
    monte_carlo_results: MonteCarloResults = Field(default_factory=MonteCarloResults)
    implied_expectations: dict[str, Any] = Field(default_factory=dict)
    underlying_assumptions: dict[str, Any] = Field(default_factory=dict)
    sotp_breakdown: dict[str, Any] | None = None
    forward_dcf: ForwardDCF | None = None
    reverse_dcf_sotp: ReverseDCFSOTP | None = None


class SummaryModule(BaseModel):
    status: ResponseStatus
    message: str
    data: dict[str, Any] | None = None
    source_refs: list[int] = Field(default_factory=list)

class LiveQuoteData(BaseModel):
    """Bucket B — real-time quote telemetry only.

    Strictly live/session fields: regular + extended-hours prices, daily
    delta, market state, and session timestamps. Structural fundamentals
    (statements, ownership) never live here so they cannot be locked by the
    short real-time cache.
    """

    symbol: str
    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    currency: str | None = None
    exchange: str | None = None
    latest_trading_day: str | None = None
    market_state: str | None = None
    extended_price: float | None = None
    extended_change: float | None = None
    extended_change_percent: float | None = None
    extended_hours_timestamp: str | None = None


class LiveQuoteResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: LiveQuoteData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[int] = Field(default_factory=list)


class StockSnapshot(BaseModel):
    """Compact, provider-backed market data for saved-stock lists."""

    ticker: str
    company_name: str | None = None
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    currency: str | None = None
    status: ResponseStatus
    as_of: str | None = None
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StockSnapshotsResponse(BaseModel):
    status: ResponseStatus
    as_of: str
    data: list[StockSnapshot] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SummaryData(BaseModel):
    quote: SummaryModule
    price_history: SummaryModule
    key_facts: SummaryModule
    company_overview: SummaryModule
    revenue_mix: SummaryModule
    supply_chain: SummaryModule
    customer_mix: SummaryModule
    performance: SummaryModule
    eps_trend: SummaryModule
    revenue_earnings: SummaryModule
    valuation_measures: SummaryModule
    financial_highlights: SummaryModule
    peer_comparison: SummaryModule


class SummaryResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: SummaryData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StatisticsData(BaseModel):
    financial_snapshot: SummaryModule
    valuation_measures: SummaryModule
    fiscal_year_information: SummaryModule
    profitability: SummaryModule
    management_effectiveness: SummaryModule
    income_statement_highlights: SummaryModule
    balance_sheet_highlights: SummaryModule
    cash_flow_highlights: SummaryModule
    stock_price_history: SummaryModule
    share_statistics: SummaryModule
    dividends_and_splits: SummaryModule
    footnotes: SummaryModule
    abbreviation_guide: SummaryModule


class StatisticsResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: StatisticsData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


StatementType = Literal["income", "balance_sheet", "cash_flow"]
StatementPeriod = Literal["annual", "quarterly"]
FinancialCellStatus = Literal["reported", "derived", "unavailable"]
FinancialRowKind = Literal["section", "parent", "line", "total", "derived"]


class FinancialStatementPeriod(BaseModel):
    key: str
    label: str
    period_end: str | None = None
    period_start: str | None = None
    fiscal_period: str | None = None
    statement_period: StatementPeriod | Literal["ttm"]
    source_ref: int | None = None


class FinancialStatementCell(BaseModel):
    value: float | int | None = None
    unit: str | None = None
    status: FinancialCellStatus
    concept: str | None = None
    taxonomy: str | None = None
    basis: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    source_ref: int | None = None
    period_start: str | None = None
    period_end: str | None = None
    duration_days: int | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filed: str | None = None
    accession: str | None = None
    calculation_method: str | None = None
    source_facts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_status: str | None = None


class FinancialStatementRow(BaseModel):
    id: str
    label: str
    depth: int = 0
    kind: FinancialRowKind
    parent_id: str | None = None
    cells: dict[str, FinancialStatementCell] = Field(default_factory=dict)


class FinancialStatementData(BaseModel):
    company_name: str | None = None
    statement: StatementType
    period: StatementPeriod
    currency: str | None = None
    unit_label: str
    taxonomy: str | None = None
    periods: list[FinancialStatementPeriod] = Field(default_factory=list)
    rows: list[FinancialStatementRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FinancialStatementResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: FinancialStatementData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CapitalAllocationEvidence(BaseModel):
    source_form: str
    source_accession: str
    source_url: str
    filing_date: str | None = None
    report_date: str | None = None
    section: str
    evidence: str


class CapitalAllocationAmountMetric(BaseModel):
    amount: float | int | None = None
    currency: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    period_type: Literal["annual", "interim"] | None = None
    status: Literal["reported", "unavailable"]
    basis: str | None = None
    concept: str | None = None
    sources: list[CapitalAllocationEvidence] = Field(default_factory=list)
    filing_evidence: list[CapitalAllocationEvidence] = Field(default_factory=list)


class ShareDilutionMetric(BaseModel):
    shares_change_percent: float | None = None
    beginning_shares: float | int | None = None
    ending_shares: float | int | None = None
    beginning_period_end: str | None = None
    ending_period_end: str | None = None
    status: Literal["derived", "unavailable"]
    basis: str | None = None
    sources: list[CapitalAllocationEvidence] = Field(default_factory=list)
    filing_evidence: list[CapitalAllocationEvidence] = Field(default_factory=list)


class CapitalAllocationMetrics(BaseModel):
    buybacks: CapitalAllocationAmountMetric
    dividends: CapitalAllocationAmountMetric
    acquisitions: CapitalAllocationAmountMetric
    debt_issuance: CapitalAllocationAmountMetric
    debt_repayment: CapitalAllocationAmountMetric
    capex: CapitalAllocationAmountMetric
    r_and_d: CapitalAllocationAmountMetric
    equity_compensation: CapitalAllocationAmountMetric
    share_dilution: ShareDilutionMetric


class AnalyzedFiling(BaseModel):
    form: str
    accession: str
    filing_date: str | None = None
    report_date: str | None = None
    source_url: str


class CapitalAllocationData(BaseModel):
    company_name: str | None = None
    fiscal_year: int | None = None
    analyzed_filings: list[AnalyzedFiling] = Field(default_factory=list)
    capital_allocation: CapitalAllocationMetrics


class CapitalAllocationResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: CapitalAllocationData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FinancialAnalysisEvidence(BaseModel):
    source_form: str | None = None
    source_accession: str | None = None
    source_url: str | None = None
    filing_date: str | None = None
    report_date: str | None = None
    section: str
    evidence: str


class DebtMaturity(BaseModel):
    year: int
    amount: float | int
    evidence: str
    source_url: str | None = None
    filing_date: str | None = None


class CreditRatingEvidence(BaseModel):
    agency: str
    rating: str
    evidence: str
    source_url: str | None = None
    filing_date: str | None = None


class DebtProfile(BaseModel):
    short_term_debt: float | int | None = None
    long_term_debt: float | int | None = None
    total_debt: float | int | None = None
    cash_and_equivalents: float | int | None = None
    net_debt: float | int | None = None
    interest_expense: float | int | None = None
    debt_issuance: float | int | None = None
    debt_repayment: float | int | None = None
    debt_maturities: list[DebtMaturity] = Field(default_factory=list)
    credit_rating: CreditRatingEvidence | None = None
    debt_to_equity: float | None = None
    debt_to_assets: float | None = None
    interest_coverage: float | None = None
    net_debt_to_operating_cash_flow: float | None = None
    sources: dict[str, list[FinancialAnalysisEvidence]] = Field(
        default_factory=dict
    )
    calculation_basis: dict[str, str] = Field(default_factory=dict)
    notes: list[FinancialAnalysisEvidence] = Field(default_factory=list)


class ShareDilutionAnalysis(BaseModel):
    basic_shares: float | int | None = None
    diluted_shares: float | int | None = None
    shares_outstanding: float | int | None = None
    weighted_average_shares: float | int | None = None
    stock_based_compensation: float | int | None = None
    share_repurchases: float | int | None = None
    equity_issuance: float | int | None = None
    net_share_change_percent: float | None = None
    dilution_risk: Literal["low", "medium", "high"] | None = None
    diluted_vs_basic_spread_percent: float | None = None
    year_over_year_basic_share_change_percent: float | None = None
    year_over_year_diluted_share_change_percent: float | None = None
    buyback_offset: dict[str, float | int | None] | None = None
    sources: dict[str, list[FinancialAnalysisEvidence]] = Field(
        default_factory=dict
    )
    calculation_basis: dict[str, str] = Field(default_factory=dict)
    notes: list[FinancialAnalysisEvidence] = Field(default_factory=list)


class DebtShareAnalysisConfidence(BaseModel):
    debt_profile: Literal["low", "medium", "high"]
    share_dilution: Literal["low", "medium", "high"]


class DebtShareAnalysisData(BaseModel):
    company_name: str | None = None
    fiscal_year: int | None = None
    debt_profile: DebtProfile
    share_dilution: ShareDilutionAnalysis
    confidence: DebtShareAnalysisConfidence


class DebtShareAnalysisResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: DebtShareAnalysisData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


HolderType = Literal[
    "institution",
    "insider",
    "director",
    "executive",
    "beneficial_owner",
    "group",
    "unknown",
]

TransactionType = Literal[
    "buy",
    "sell",
    "grant",
    "award",
    "exercise",
    "gift",
    "tax_withholding",
    "conversion",
    "other",
]


class MajorHolder(BaseModel):
    holder_name: str
    shares_held: int | None = None
    ownership_percent: float | None = None
    ownership_display_note: str | None = None
    holder_type: HolderType
    as_of_date: str | None = None
    filing_type: str
    filing_date: str
    accession_number: str
    source_url: str


class InsiderOwnershipSummary(BaseModel):
    insider_shares: int | None = None
    insider_ownership_percent: float | None = None
    ownership_display_note: str | None = None
    as_of_date: str | None = None
    calculation_method: Literal[
        "reported_group_total",
        "calculated_from_individuals",
        "unavailable",
    ]
    source_url: str | None = None


class InsiderRelationship(BaseModel):
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    is_other: bool
    officer_title: str | None = None


class InsiderTransaction(BaseModel):
    owner_name: str
    owner_cik: str | None = None
    relationship: InsiderRelationship
    transaction_date: str | None = None
    filing_date: str
    transaction_code: str | None = None
    transaction_type: TransactionType
    security_title: str | None = None
    shares_transacted: float | None = None
    price_per_share: float | None = None
    transaction_value: float | None = None
    acquired_or_disposed: Literal["A", "D"] | None = None
    shares_owned_after: float | None = None
    ownership_nature: Literal["direct", "indirect", "unknown"]
    derivative_security: bool
    accession_number: str
    source_url: str


class InstitutionalHolder(BaseModel):
    institution_name: str
    manager_cik: str
    shares_held: int
    reported_value_usd: float | None = None
    ownership_percent: float | None = None
    portfolio_weight_percent: float | None = None
    report_period: str
    filing_date: str
    accession_number: str
    source_url: str
    cusip: str | None = None
    figi: str | None = None
    class_title: str | None = None
    mapping_method: str
    mapping_confidence: float = Field(ge=0, le=1)


class OwnershipBreakdown(BaseModel):
    institutional_percent: float | None = None
    insider_percent: float | None = None
    other_public_percent: float | None = None
    institutional_as_of_date: str | None = None
    insider_as_of_date: str | None = None
    shares_outstanding_as_of_date: str | None = None
    shares_outstanding: int | None = None
    shares_outstanding_source: str | None = None
    shares_outstanding_distance_days: int | None = None
    institutional_ownership_status: Literal[
        "available",
        "temporarily_unavailable",
    ] = "temporarily_unavailable"
    institutional_ownership_reason: str | None = None
    is_estimated: bool
    warnings: list[str] = Field(default_factory=list)


class HoldersAvailability(BaseModel):
    major_holders: Literal[
        "available",
        "unavailable",
        "temporarily_unavailable",
        "identifier_mapping_required",
    ]
    insider_ownership: Literal[
        "available",
        "unavailable",
        "temporarily_unavailable",
        "identifier_mapping_required",
    ]
    insider_transactions: Literal[
        "available",
        "unavailable",
        "temporarily_unavailable",
        "identifier_mapping_required",
    ]
    institutional_holders: Literal[
        "available",
        "unavailable",
        "temporarily_unavailable",
        "identifier_mapping_required",
    ]


class HoldersData(BaseModel):
    company_name: str | None = None
    ownership_breakdown: OwnershipBreakdown
    insider_ownership: InsiderOwnershipSummary
    major_holders: list[MajorHolder] = Field(default_factory=list)
    recent_insider_transactions: list[InsiderTransaction] = Field(
        default_factory=list
    )
    institutional_holders: list[InstitutionalHolder] = Field(default_factory=list)
    institutional_report_period: str | None = None
    institutional_total: int = 0
    institutional_manager_count: int = 0
    institutional_limit: int = 25
    institutional_offset: int = 0
    data_availability: HoldersAvailability
    transaction_total: int = 0
    transaction_limit: int = 25
    transaction_offset: int = 0


class HoldersResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: HoldersData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProfileValue(BaseModel):
    value: str | int | float | None = None
    status: Literal["reported", "unavailable"]
    provider: str | None = None
    source_url: str | None = None
    fetched_at: str | None = None
    filing_date: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    source_ref: int | None = None
    source_timestamp: str | None = None


class ExecutiveProfile(BaseModel):
    name: str | None = None
    title: str | None = None
    role: str | None = None
    pay: float | int | None = None
    exercised_value: float | int | None = None
    compensation: float | int | None = None
    year_born: int | None = None
    age: int | None = None
    reporting_period: str | None = None
    provider: str | None = None
    filing_date: str | None = None
    filing_url: str | None = None
    evidence: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_ref: int | None = None


class ExecutiveCompensationProfile(BaseModel):
    name: str
    year: int | None = None
    salary: float | int | None = None
    bonus: float | int | None = None
    stock_awards: float | int | None = None
    option_awards: float | int | None = None
    non_equity_incentive_plan_compensation: float | int | None = None
    all_other_compensation: float | int | None = None
    total_compensation: float | int | None = None
    provider: str
    filing_date: str | None = None
    filing_url: str
    evidence: str
    confidence: float = Field(ge=0, le=1)


class CompanyContactProfile(BaseModel):
    street_address: ProfileValue
    city_state_postal_code: ProfileValue
    country: ProfileValue
    phone_number: ProfileValue
    company_website: ProfileValue


class CompanyClassificationProfile(BaseModel):
    sector: ProfileValue
    industry: ProfileValue
    full_time_employees: ProfileValue
    founded: ProfileValue
    headquarters_region: ProfileValue
    is_adr: ProfileValue
    adr_ratio: ProfileValue


class CompanyDescriptionProfile(BaseModel):
    text: str | None = None
    status: Literal["reported", "unavailable"]
    provider: str | None = None
    source_url: str | None = None
    filing_date: str | None = None
    fetched_at: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    source_ref: int | None = None
    source_timestamp: str | None = None


class GovernanceItemProfile(BaseModel):
    name: str
    role: str | None = None
    provider: str
    filing_date: str | None = None
    filing_url: str
    evidence: str
    confidence: float = Field(ge=0, le=1)


class GovernanceCommitteeProfile(BaseModel):
    name: str
    members: list[str] = Field(default_factory=list)
    provider: str
    filing_date: str | None = None
    filing_url: str
    evidence: str
    confidence: float = Field(ge=0, le=1)


class GovernanceVotingMatterProfile(BaseModel):
    matter: str
    provider: str
    filing_date: str | None = None
    filing_url: str
    evidence: str
    confidence: float = Field(ge=0, le=1)


class GovernanceProfile(BaseModel):
    overall_risk_score: ProfileValue
    scale_interpretation: str
    audit_risk_score: ProfileValue
    board_risk_score: ProfileValue
    shareholder_rights_risk_score: ProfileValue
    compensation_risk_score: ProfileValue
    provider: str | None = None
    score_date: str | None = None
    status: Literal["reported", "unavailable"]
    directors: list[GovernanceItemProfile] = Field(default_factory=list)
    committees: list[GovernanceCommitteeProfile] = Field(default_factory=list)
    voting_matters: list[GovernanceVotingMatterProfile] = Field(default_factory=list)
    notes: list[GovernanceItemProfile] = Field(default_factory=list)


class ProfileEvent(BaseModel):
    event_type: str
    title: str
    event_date: str | None = None
    source: str | None = None
    provider: str | None = None
    source_url: str | None = None
    fetched_at: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_ref: int | None = None


class ProfileFiling(BaseModel):
    form: str
    filing_date: str | None = None
    report_date: str | None = None
    description: str
    accession_number: str | None = None
    source_url: str | None = None
    source_ref: int | None = None


class ProfileData(BaseModel):
    company_name: str | None = None
    normalized_ticker: str
    profile_sources: dict[str, bool] = Field(default_factory=dict)
    basic_profile: dict[str, ProfileValue] = Field(default_factory=dict)
    exchange: str | None = None
    currency: str | None = None
    logo: str | None = None
    logo_url: str | None = None
    fmp_logo_url: str | None = None
    ipo_date: str | None = None
    market_capitalization: float | None = None
    finnhub_industry: str | None = None
    market_state: str | None = None
    current_price: float | None = None
    extended_price: float | None = None
    extended_change: float | None = None
    extended_change_percent: float | None = None
    extended_hours_timestamp: str | None = None
    price_change: float | None = None
    price_change_percent: float | None = None
    key_executives: list[ExecutiveProfile] = Field(default_factory=list)
    executive_compensation: list[ExecutiveCompensationProfile] = Field(
        default_factory=list
    )
    contact: CompanyContactProfile
    classification: CompanyClassificationProfile
    description: CompanyDescriptionProfile
    governance: GovernanceProfile
    upcoming_events: list[ProfileEvent] = Field(default_factory=list)
    recent_events_and_filings: list[ProfileFiling] = Field(default_factory=list)
    data_availability: dict[str, ResponseStatus] = Field(default_factory=dict)
    unavailable: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    ticker: str
    status: ResponseStatus
    as_of: str | None
    data: ProfileData
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
