export type ResponseStatus =
  | "success"
  | "partial"
  | "unavailable"
  | "missing_input"
  | "stale"
  | "error";

export interface SourceRecord {
  provider: string;
  source_url: string | null;
  source_timestamp: string | null;
  fetched_at: string;
  is_stale: boolean;
}

export interface SummaryModule {
  status: ResponseStatus;
  message: string;
  data: Record<string, unknown> | null;
  source_refs: number[];
}

export interface SummaryData {
  quote: SummaryModule;
  price_history: SummaryModule;
  key_facts: SummaryModule;
  company_overview: SummaryModule;
  revenue_mix: SummaryModule;
  supply_chain: SummaryModule;
  customer_mix: SummaryModule;
  performance: SummaryModule;
  eps_trend: SummaryModule;
  revenue_earnings: SummaryModule;
  valuation_measures: SummaryModule;
  financial_highlights: SummaryModule;
  peer_comparison: SummaryModule;
}

export interface SummaryResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: SummaryData;
  sources: SourceRecord[];
  warnings: string[];
}

export interface StatisticsData {
  financial_snapshot: SummaryModule;
  valuation_measures: SummaryModule;
  fiscal_year_information: SummaryModule;
  profitability: SummaryModule;
  management_effectiveness: SummaryModule;
  income_statement_highlights: SummaryModule;
  balance_sheet_highlights: SummaryModule;
  cash_flow_highlights: SummaryModule;
  stock_price_history: SummaryModule;
  share_statistics: SummaryModule;
  dividends_and_splits: SummaryModule;
  footnotes: SummaryModule;
  abbreviation_guide: SummaryModule;
}

export interface StatisticsResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: StatisticsData;
  sources: SourceRecord[];
  warnings: string[];
}

export type StatementType = "income" | "balance_sheet" | "cash_flow";
export type StatementPeriod = "annual" | "quarterly";
export type FinancialsView = StatementType | "debt_share";
export type FinancialCellStatus = "reported" | "derived" | "unavailable";
export type FinancialRowKind = "section" | "parent" | "line" | "total" | "derived";

export interface FinancialStatementPeriod {
  key: string;
  label: string;
  period_end: string | null;
  period_start: string | null;
  fiscal_period: string | null;
  statement_period: StatementPeriod | "ttm";
  source_ref: number | null;
}

export interface FinancialStatementCell {
  value: number | null;
  unit: string | null;
  status: FinancialCellStatus;
  concept: string | null;
  taxonomy: string | null;
  basis: string | null;
  input_refs: string[];
  source_ref: number | null;
  period_start: string | null;
  period_end: string | null;
  duration_days: number | null;
  fiscal_year: number | null;
  fiscal_period: string | null;
  form: string | null;
  filed: string | null;
  accession: string | null;
  calculation_method: string | null;
  source_facts: Record<string, unknown>[];
  warnings: string[];
  data_status: string | null;
}

export interface FinancialStatementRow {
  id: string;
  label: string;
  depth: number;
  kind: FinancialRowKind;
  parent_id: string | null;
  cells: Record<string, FinancialStatementCell>;
}

export interface FinancialStatementResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: {
    company_name: string | null;
    statement: StatementType;
    period: StatementPeriod;
    currency: string | null;
    unit_label: string;
    taxonomy: string | null;
    periods: FinancialStatementPeriod[];
    rows: FinancialStatementRow[];
    notes: string[];
  };
  sources: SourceRecord[];
  warnings: string[];
}

export interface DcfMetric {
  name?: string;
  value: number | null;
  status: string;
  unit?: string | null;
  currency?: string | null;
  basis?: string | null;
  confidence?: string | null;
  warnings?: string[];
  lineage?: Record<string, string | number | null>;
  calculation_method?: string | null;
  source_facts?: Record<string, unknown>[];
  evidence?: Record<string, unknown>[];
  source_freshness?: Record<string, string | number | boolean | null>;
  user_confirmation_required?: boolean;
}

export interface DcfStartingBasis {
  basis_type: "latest_ttm" | "latest_fiscal_year" | "normalized";
  selected_by: "system" | "user";
  period_start?: string | null;
  period_end?: string | null;
  calculation_method?: string | null;
  source_facts?: Record<string, unknown>[];
  data_quality: "high" | "medium" | "low" | "insufficient";
  reason_codes: string[];
  warnings: string[];
  user_overridden: boolean;
}

export interface DcfScenario {
  name: string;
  status: string;
  lifecycle_state: "locked" | "available" | "initialized" | "incomplete" | "valid" | "invalid";
  can_calculate: boolean;
  can_initialize_from_base?: boolean;
  can_initialize_dependents?: boolean;
  locked_reason?: string | null;
  assumptions: Record<string, number | null>;
  transformation: Record<string, unknown>;
  missing_inputs: string[];
  validation_errors: string[];
  readiness?: {
    state: string;
    can_calculate: boolean;
    missing_inputs: string[];
    validation_errors: string[];
    basis?: string;
  };
}

export interface DcfInputsResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: {
    company_name?: string | null;
    model_version: string;
    modes: Record<string, { status: string; editable_fields?: string[] }>;
    selected_starting_basis: DcfStartingBasis | null;
    starting_basis_options: DcfStartingBasis[];
    historical_metrics: {
      annual: Record<string, unknown>[];
      latest_ttm: Record<string, DcfMetric>;
    };
    equity_bridge_inputs: Record<string, DcfMetric | string | null>;
    assumption_suggestions: Record<string, DcfMetric>;
    scenarios: Record<string, DcfScenario>;
    wacc: {
      status: string;
      components: Record<string, DcfMetric>;
      warnings: string[];
      final_wacc?: number | null;
    };
    sensitivity: {
      status: string;
      tables: Record<string, unknown[]>;
      warnings: string[];
    };
    sbc_and_dilution: {
      status?: string;
      ttm_stock_based_compensation?: DcfMetric;
      latest_period_end_shares?: DcfMetric;
      methods?: {
        id: string;
        label: string;
        status: string;
        double_counting_warning: string | null;
      }[];
      warnings?: string[];
    };
    normalization_review: {
      status: string;
      options?: string[];
      warnings: string[];
    };
    source_lineage: Record<string, string | number | boolean | null>[];
    validation: {
      status: string;
      can_calculate_base?: boolean;
      base_state?: string;
      missing_inputs: string[];
      validation_errors?: string[];
      warnings: string[];
    };
    data_quality: {
      label: string;
      reason_codes: string[];
      warnings: string[];
    };
  };
  sources: SourceRecord[];
  warnings: string[];
}

export interface CapitalAllocationEvidence {
  source_form: string;
  source_accession: string;
  source_url: string;
  filing_date: string | null;
  report_date: string | null;
  section: string;
  evidence: string;
}

export interface CapitalAllocationAmountMetric {
  amount: number | null;
  currency: string | null;
  period_start: string | null;
  period_end: string | null;
  period_type: "annual" | "interim" | null;
  status: "reported" | "unavailable";
  basis: string | null;
  concept: string | null;
  sources: CapitalAllocationEvidence[];
  filing_evidence: CapitalAllocationEvidence[];
}

export interface ShareDilutionMetric {
  shares_change_percent: number | null;
  beginning_shares: number | null;
  ending_shares: number | null;
  beginning_period_end: string | null;
  ending_period_end: string | null;
  status: "derived" | "unavailable";
  basis: string | null;
  sources: CapitalAllocationEvidence[];
  filing_evidence: CapitalAllocationEvidence[];
}

export interface CapitalAllocationResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: {
    company_name: string | null;
    fiscal_year: number | null;
    analyzed_filings: {
      form: string;
      accession: string;
      filing_date: string | null;
      report_date: string | null;
      source_url: string;
    }[];
    capital_allocation: {
      buybacks: CapitalAllocationAmountMetric;
      dividends: CapitalAllocationAmountMetric;
      acquisitions: CapitalAllocationAmountMetric;
      debt_issuance: CapitalAllocationAmountMetric;
      debt_repayment: CapitalAllocationAmountMetric;
      capex: CapitalAllocationAmountMetric;
      r_and_d: CapitalAllocationAmountMetric;
      equity_compensation: CapitalAllocationAmountMetric;
      share_dilution: ShareDilutionMetric;
    };
  };
  sources: SourceRecord[];
  warnings: string[];
}

export interface FinancialAnalysisEvidence {
  source_form: string | null;
  source_accession: string | null;
  source_url: string | null;
  filing_date: string | null;
  report_date: string | null;
  section: string;
  evidence: string;
}

export interface DebtMaturity {
  year: number;
  amount: number;
  evidence: string;
  source_url: string | null;
  filing_date: string | null;
}

export interface CreditRatingEvidence {
  agency: string;
  rating: string;
  evidence: string;
  source_url: string | null;
  filing_date: string | null;
}

export interface DebtProfile {
  short_term_debt: number | null;
  long_term_debt: number | null;
  total_debt: number | null;
  cash_and_equivalents: number | null;
  net_debt: number | null;
  interest_expense: number | null;
  debt_issuance: number | null;
  debt_repayment: number | null;
  debt_maturities: DebtMaturity[];
  credit_rating: CreditRatingEvidence | null;
  debt_to_equity: number | null;
  debt_to_assets: number | null;
  interest_coverage: number | null;
  net_debt_to_operating_cash_flow: number | null;
  sources: Record<string, FinancialAnalysisEvidence[]>;
  calculation_basis: Record<string, string>;
  notes: FinancialAnalysisEvidence[];
}

export interface ShareDilutionAnalysis {
  basic_shares: number | null;
  diluted_shares: number | null;
  shares_outstanding: number | null;
  weighted_average_shares: number | null;
  stock_based_compensation: number | null;
  share_repurchases: number | null;
  equity_issuance: number | null;
  net_share_change_percent: number | null;
  dilution_risk: "low" | "medium" | "high" | null;
  diluted_vs_basic_spread_percent: number | null;
  year_over_year_basic_share_change_percent: number | null;
  year_over_year_diluted_share_change_percent: number | null;
  buyback_offset: {
    share_repurchases: number | null;
    stock_based_compensation: number | null;
    offset_amount: number | null;
    offset_ratio: number | null;
  } | null;
  sources: Record<string, FinancialAnalysisEvidence[]>;
  calculation_basis: Record<string, string>;
  notes: FinancialAnalysisEvidence[];
}

export interface DebtShareAnalysisResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: {
    company_name: string | null;
    fiscal_year: number | null;
    debt_profile: DebtProfile;
    share_dilution: ShareDilutionAnalysis;
    confidence: {
      debt_profile: "low" | "medium" | "high";
      share_dilution: "low" | "medium" | "high";
    };
  };
  sources: SourceRecord[];
  warnings: string[];
}

export interface QuoteData {
  company_name: string | null;
  exchange: string | null;
  currency: string | null;
  market_state: string | null;
  price: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  latest_trading_day: string | null;
  day_low: number | null;
  day_high: number | null;
  regularMarketPrice: number | null;
  regularMarketChangePercent: number | null;
  extendedPrice: number | null;
  extendedChange: number | null;
  extendedChangePercent: number | null;
  extendedHoursTimestamp: string | null;
}

export interface PricePoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface PriceHistoryData {
  interval: string;
  points: PricePoint[];
}

export interface FilingPoint {
  period: string;
  start?: string | null;
  end: string;
  value: number;
  unit: string | null;
  concept?: string | null;
  form?: string | null;
  filed?: string | null;
  accession?: string | null;
}

export interface RevenueEarningsPoint {
  period: string;
  end: string;
  revenue: number;
  earnings: number | null;
  currency: string | null;
}

export interface RevenueEarningsData {
  period_type: "annual" | "quarterly";
  points: RevenueEarningsPoint[];
  currency: string | null;
}

export interface RevenueMixItem {
  name: string;
  segment?: string;
  product?: string;
  region?: string;
  end_market?: string;
  member: string;
  revenue: number;
  percentage: number;
  currency: string;
  period_end: string;
  confidence: number;
  evidence: string;
  filing_url: string | null;
  filing_date: string | null;
  source: "sec_companyfacts" | "sec_filing_inline_xbrl";
  axis: string;
  concept: string;
  coverage: "complete" | "partial";
}

export interface RevenueMixPeriod {
  fiscal_year: number;
  period_end: string;
  total_revenue: number;
  currency: string;
  items: RevenueMixItem[];
}

export type RevenueMixDimension =
  | "business_segments"
  | "products"
  | "geography"
  | "end_markets";

export interface RevenueMixData {
  ticker: string;
  fiscal_year: number | null;
  revenue_mix: Record<RevenueMixDimension, RevenueMixItem[]>;
  periods: Record<RevenueMixDimension, RevenueMixPeriod[]>;
  dimension_metadata: Partial<
    Record<
      RevenueMixDimension,
      {
        total_revenue: number;
        currency: string;
        axis: string;
        concept: string;
        source: "sec_companyfacts" | "sec_filing_inline_xbrl";
        coverage: "complete" | "partial";
      }
    >
  >;
}

export interface SupplyChainEvidence {
  confidence: number;
  concentration_qualifier: string | null;
  evidence: string;
  section: string | null;
  source_form: string;
  source_accession: string;
  source_url: string;
  filing_date: string | null;
  report_date: string | null;
  percentage: number | null;
}

export interface SupplyChainSupplier extends SupplyChainEvidence {
  name: string;
  role: string;
  relationship_type: string;
  dependency_type: string;
}

export interface SupplyChainLocation extends SupplyChainEvidence {
  country: string;
  role: string;
}

export interface RawMaterialDependency extends SupplyChainEvidence {
  material: string;
  dependency_type: string;
}

export interface CustomerConcentration extends SupplyChainEvidence {
  name: string | null;
  basis: string;
}

export interface SupplyChainRisk extends SupplyChainEvidence {
  type: string;
  severity: "high" | "medium" | "low" | "unknown";
}

export interface SupplyChainData {
  ticker: string;
  fiscal_year: number | null;
  extraction?: {
    method: "ai" | "deterministic";
    provider: string | null;
    model: string | null;
    extractor_version: string | null;
    cache_source: "fresh" | "memory" | "persistent" | null;
    fallback_used: boolean;
    fallback_reason: string | null;
    candidate_passages?: number;
  };
  analyzed_filings: {
    form: string;
    accession: string;
    filing_date: string | null;
    report_date: string | null;
    source_url: string;
  }[];
  supply_chain_exposure: {
    suppliers: SupplyChainSupplier[];
    manufacturing_locations: SupplyChainLocation[];
    raw_material_dependencies: RawMaterialDependency[];
    customer_concentrations: CustomerConcentration[];
    risks: SupplyChainRisk[];
  };
}

export interface CustomerMixEvidence {
  confidence: number;
  evidence: string;
  section: string | null;
  source_form: string;
  source_accession: string;
  source_url: string;
  filing_date: string | null;
  report_date: string | null;
}

export interface CustomerMixData {
  ticker: string;
  fiscal_year: number | null;
  extraction?: {
    method: "ai" | "deterministic";
    provider: string | null;
    model: string | null;
    extractor_version: string | null;
    cache_source: "fresh" | "memory" | "persistent" | null;
    attempted_models: string[];
    model_failover_used: boolean;
    model_failover_reason: string | null;
    fallback_used: boolean;
    fallback_reason: string | null;
    candidate_passages?: number;
  };
  analyzed_filings: {
    form: string;
    accession: string;
    filing_date: string | null;
    report_date: string | null;
    source_url: string;
  }[];
  customer_mix: {
    major_customers: (CustomerMixEvidence & {
      name: string | null;
      customer_count: number | null;
      revenue_percentage: number | null;
      percentage: number | null;
      percentage_basis: "revenue" | "accounts_receivable" | "not_specified";
      percentage_scope?:
        | "single_customer"
        | "each_customer"
        | "customer_group";
      period?: string | null;
      rank?: string | null;
    })[];
    customer_types: (CustomerMixEvidence & {
      type: string;
      label?: string | null;
      exposure: "high" | "medium" | "low" | "not_quantified";
      revenue_percentage: number | null;
    })[];
    channel_dependencies: (CustomerMixEvidence & {
      type: string;
      name: string | null;
      exposure: "high" | "medium" | "low" | "not_quantified";
      revenue_percentage: number | null;
    })[];
    end_markets: (CustomerMixEvidence & {
      market: string;
      exposure: "high" | "medium" | "low" | "not_quantified";
      revenue_percentage: number | null;
    })[];
    risks: (CustomerMixEvidence & {
      type: string;
      severity: "high" | "medium" | "unknown";
      percentage?: number | null;
      percentage_basis?: "revenue" | "accounts_receivable" | "not_specified";
    })[];
  };
}

export interface EpsTrendData {
  points: FilingPoint[];
}

export interface KeyFactsData {
  previous_close: number | null;
  day_range: { low: number | null; high: number | null };
  range_label?: string;
  week_52_range: { low: number | null; high: number | null };
  market_cap: DerivedMetric;
  pe_ratio: DerivedMetric;
  eps: FilingPoint | null;
  dividend_yield: DerivedMetric & {
    period_type: "ttm" | "fiscal" | null;
    dividend_per_share: number | null;
    period_end: string | null;
  };
  next_earnings: string | null;
}

export interface CompanyOverviewData {
  company_name: string | null;
  cik?: string | null;
  description: string | null;
  sector: string | null;
  industry: string | null;
  exchange?: string | null;
  fiscal_year_end?: string | null;
  state_of_incorporation?: string | null;
  entity_type?: string | null;
  filer_category?: string | null;
}

export interface DerivedMetric {
  value: number | null;
  status: "provider" | "derived" | "unavailable";
  basis: string;
  input_refs: string[];
}

export interface FinancialHighlightsData {
  metrics: {
    revenue_ttm: DerivedMetric;
    profit_margin: DerivedMetric;
    return_on_assets: DerivedMetric;
    return_on_equity: DerivedMetric;
    net_income_to_common: DerivedMetric;
    diluted_eps: DerivedMetric;
    total_cash: DerivedMetric;
    total_debt_to_equity: DerivedMetric;
    levered_free_cash_flow: DerivedMetric;
  };
  base_metrics: {
    revenue_ttm: number | null;
    net_income_ttm: number | null;
    total_assets_mrq: number | null;
    total_equity_mrq: number | null;
    diluted_shares_ttm: number | null;
    total_cash_mrq: number | null;
    total_debt_mrq: number | null;
    free_cash_flow_ttm: number | null;
    currency: string | null;
  };
}

export interface ValuationMeasuresData {
  metrics: {
    market_cap: DerivedMetric;
    enterprise_value: DerivedMetric;
    trailing_pe: DerivedMetric;
    forward_pe: DerivedMetric;
    peg_ratio: DerivedMetric;
    price_to_sales: DerivedMetric;
    price_to_book: DerivedMetric;
    ev_to_revenue: DerivedMetric;
    ev_to_ebitda: DerivedMetric;
  };
  base_metrics: {
    shares_outstanding_mrq: number | null;
    total_debt_mrq: number | null;
    total_cash_mrq: number | null;
    net_income_ttm: number | null;
    revenue_ttm: number | null;
    book_value_per_share_mrq: number | null;
    ebitda_ttm: number | null;
    forward_pe: number | null;
    peg_ratio: number | null;
  };
}

export interface PerformanceData {
  returns: {
    ytd: number | null;
    one_year: number | null;
    three_year: number | null;
    five_year: number | null;
  };
  benchmark: null;
}

export type HolderAvailability =
  | "available"
  | "unavailable"
  | "temporarily_unavailable"
  | "identifier_mapping_required";

export interface MajorHolder {
  holder_name: string;
  shares_held: number | null;
  ownership_percent: number | null;
  ownership_display_note: string | null;
  holder_type: "institution" | "insider" | "director" | "executive" | "beneficial_owner" | "group" | "unknown";
  as_of_date: string | null;
  filing_type: string;
  filing_date: string;
  accession_number: string;
  source_url: string;
}

export interface InsiderOwnershipSummary {
  insider_shares: number | null;
  insider_ownership_percent: number | null;
  ownership_display_note: string | null;
  as_of_date: string | null;
  calculation_method: "reported_group_total" | "calculated_from_individuals" | "unavailable";
  source_url: string | null;
}

export interface InsiderTransaction {
  owner_name: string;
  owner_cik: string | null;
  relationship: {
    is_director: boolean;
    is_officer: boolean;
    is_ten_percent_owner: boolean;
    is_other: boolean;
    officer_title: string | null;
  };
  transaction_date: string | null;
  filing_date: string;
  transaction_code: string | null;
  transaction_type: "buy" | "sell" | "grant" | "award" | "exercise" | "gift" | "tax_withholding" | "conversion" | "other";
  security_title: string | null;
  shares_transacted: number | null;
  price_per_share: number | null;
  transaction_value: number | null;
  acquired_or_disposed: "A" | "D" | null;
  shares_owned_after: number | null;
  ownership_nature: "direct" | "indirect" | "unknown";
  derivative_security: boolean;
  accession_number: string;
  source_url: string;
}

export interface InstitutionalHolder {
  institution_name: string;
  manager_cik: string;
  shares_held: number;
  reported_value_usd: number | null;
  ownership_percent: number | null;
  portfolio_weight_percent: number | null;
  report_period: string;
  filing_date: string;
  accession_number: string;
  source_url: string;
  cusip: string | null;
  figi: string | null;
  class_title: string | null;
  mapping_method: string;
  mapping_confidence: number;
}

export interface HoldersResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: {
    company_name: string | null;
    ownership_breakdown: {
      institutional_percent: number | null;
      insider_percent: number | null;
      other_public_percent: number | null;
      institutional_as_of_date: string | null;
      insider_as_of_date: string | null;
      shares_outstanding_as_of_date: string | null;
      shares_outstanding: number | null;
      shares_outstanding_source: string | null;
      shares_outstanding_distance_days: number | null;
      institutional_ownership_status:
        | "available"
        | "temporarily_unavailable";
      institutional_ownership_reason: string | null;
      is_estimated: boolean;
      warnings: string[];
    };
    insider_ownership: InsiderOwnershipSummary;
    major_holders: MajorHolder[];
    recent_insider_transactions: InsiderTransaction[];
    institutional_holders: InstitutionalHolder[];
    institutional_report_period: string | null;
    institutional_total: number;
    institutional_manager_count: number;
    institutional_limit: number;
    institutional_offset: number;
    data_availability: {
      major_holders: HolderAvailability;
      insider_ownership: HolderAvailability;
      insider_transactions: HolderAvailability;
      institutional_holders: HolderAvailability;
    };
    transaction_total: number;
    transaction_limit: number;
    transaction_offset: number;
  };
  sources: SourceRecord[];
  warnings: string[];
}

export interface ProfileValue {
  value: string | number | null;
  status: "reported" | "unavailable";
  provider: string | null;
  source_url: string | null;
  fetched_at: string | null;
  filing_date: string | null;
  confidence: number | null;
  reason: string | null;
  source_ref: number | null;
  source_timestamp: string | null;
}

export interface ExecutiveProfile {
  name: string | null;
  title: string | null;
  role: string | null;
  pay: number | null;
  exercised_value: number | null;
  compensation: number | null;
  year_born: number | null;
  age: number | null;
  reporting_period: string | null;
  provider: string | null;
  filing_date: string | null;
  filing_url: string | null;
  evidence: string | null;
  confidence: number | null;
  source_ref: number | null;
}

export interface ExecutiveCompensationProfile {
  name: string;
  year: number | null;
  salary: number | null;
  bonus: number | null;
  stock_awards: number | null;
  option_awards: number | null;
  non_equity_incentive_plan_compensation: number | null;
  all_other_compensation: number | null;
  total_compensation: number | null;
  provider: string;
  filing_date: string | null;
  filing_url: string;
  evidence: string;
  confidence: number;
}

export interface GovernanceItemProfile {
  name: string;
  role: string | null;
  provider: string;
  filing_date: string | null;
  filing_url: string;
  evidence: string;
  confidence: number;
}

export interface GovernanceCommitteeProfile {
  name: string;
  members: string[];
  provider: string;
  filing_date: string | null;
  filing_url: string;
  evidence: string;
  confidence: number;
}

export interface GovernanceVotingMatterProfile {
  matter: string;
  provider: string;
  filing_date: string | null;
  filing_url: string;
  evidence: string;
  confidence: number;
}

export interface ProfileEvent {
  event_type: string;
  title: string;
  event_date: string | null;
  source: string | null;
  provider: string | null;
  source_url: string | null;
  fetched_at: string | null;
  confidence: number | null;
  source_ref: number | null;
}

export interface ProfileFiling {
  form: string;
  filing_date: string | null;
  report_date: string | null;
  description: string;
  accession_number: string | null;
  source_url: string | null;
  source_ref: number | null;
}

export interface ProfileResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: {
    company_name: string | null;
    normalized_ticker: string;
    profile_sources: Record<string, boolean>;
    basic_profile: Record<string, ProfileValue>;
    exchange: string | null;
    currency: string | null;
    logo: string | null;
    ipo_date: string | null;
    market_capitalization: number | null;
    finnhub_industry: string | null;
    market_state: string | null;
    current_price: number | null;
    extended_price?: number | null;
    extended_change?: number | null;
    extended_change_percent?: number | null;
    extended_hours_timestamp?: string | null;
    price_change: number | null;
    price_change_percent: number | null;
    key_executives: ExecutiveProfile[];
    executive_compensation: ExecutiveCompensationProfile[];
    contact: {
      street_address: ProfileValue;
      city_state_postal_code: ProfileValue;
      country: ProfileValue;
      phone_number: ProfileValue;
      company_website: ProfileValue;
    };
    classification: {
      sector: ProfileValue;
      industry: ProfileValue;
      full_time_employees: ProfileValue;
      founded: ProfileValue;
      headquarters_region: ProfileValue;
    };
    description: {
      text: string | null;
      status: "reported" | "unavailable";
      provider: string | null;
      source_url: string | null;
      filing_date: string | null;
      fetched_at: string | null;
      confidence: number | null;
      reason: string | null;
      source_ref: number | null;
      source_timestamp: string | null;
    };
    governance: {
      overall_risk_score: ProfileValue;
      scale_interpretation: string;
      audit_risk_score: ProfileValue;
      board_risk_score: ProfileValue;
      shareholder_rights_risk_score: ProfileValue;
      compensation_risk_score: ProfileValue;
      provider: string | null;
      score_date: string | null;
      status: "reported" | "unavailable";
      directors: GovernanceItemProfile[];
      committees: GovernanceCommitteeProfile[];
      voting_matters: GovernanceVotingMatterProfile[];
      notes: GovernanceItemProfile[];
    };
    upcoming_events: ProfileEvent[];
    recent_events_and_filings: ProfileFiling[];
    data_availability: Record<string, ResponseStatus>;
    unavailable: string[];
  };
  sources: SourceRecord[];
  warnings: string[];
}

/* ── Bucket B: live quote telemetry (SWR-hydrated) ──────────── */
export interface LiveQuoteData {
  symbol: string;
  price: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  currency: string | null;
  exchange: string | null;
  latest_trading_day: string | null;
  market_state: string | null;
  extended_price: number | null;
  extended_change: number | null;
  extended_change_percent: number | null;
  extended_hours_timestamp: string | null;
}

export interface LiveQuoteResponse {
  ticker: string;
  status: ResponseStatus;
  as_of: string | null;
  data: LiveQuoteData;
  sources: SourceRecord[];
  warnings: string[];
}
