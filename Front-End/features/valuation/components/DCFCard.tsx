import { Info, LineChart as LineChartIcon } from "lucide-react"
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"

export type ValuationMethodology =
  | "Capitalized R&D DCF"
  | "Regulatory FCFE"
  | "Normalized Median DCF"
  | "Standard Driver-Based DCF"
  | string

export interface EngineMetadata {
  model_version?: string
  forecast_basis?: string
  consensus_coverage?: Record<string, unknown>
  consensus_horizon_sensitivity?: {
    method?: string
    warning_code?: string
    warning_threshold_percentage?: number
    assessment?: "MATERIAL_DEPENDENCY" | "STABLE_UNDER_TEST" | string
    diagnostic_only?: boolean
    primary_value_basis?: string
    source_refs?: string[]
    full_consensus_years?: number[]
    removed_consensus_year?: number
    last_consensus_revenue_growth_percentage?: number | null
    last_consensus_revenue_growth_basis?: string | null
    last_consensus_revenue_analyst_count?: number | null
    full_fair_value?: number
    truncated_fair_value?: number
    absolute_delta?: number
    relative_delta_percentage?: number
    warning_triggered?: boolean
  }
  capitalized_rnd_adjustment?: number
  capitalized_rnd_asset?: number
  rnd_ebit_adjustment?: number
  rnd_nopat_adjustment?: number
  rnd_normalization_basis?: string
  adjusted_ebit_margin?: number
  assumed_amortization_years?: number
  terminal_roic?: number
  terminal_reinvestment_rate?: number
  tier_1_capital_ratio_used?: number
  projected_loan_growth?: number
  discount_rate_type?: string
  "10_year_historical_median_margin"?: number
  normalized_base_ebit_generated?: number
  fallback_reason?: string
  projection_years?: number
}

export interface ApiProjectionYear {
  year: number
  fiscal_year?: number | null
  forecast_stage?: string | null
  source_status?: string | null
  revenue?: number | null
  revenue_growth?: number | null
  net_income?: number | null
  net_income_growth?: number | null
  ebit_margin?: number | null
  ebit?: number | null
  reported_consensus_ebit?: number | null
  reported_consensus_ebit_margin?: number | null
  rnd_ebit_margin_adjustment?: number | null
  tax_rate?: number | null
  nopat?: number | null
  sales_to_capital_ratio?: number | null
  capital_deduction_label?: string | null
  capital_deduction_value?: number | null
  unlevered_free_cash_flow?: number | null
  free_cash_flow_to_equity?: number | null
  wacc?: number | null
  discount_factor?: number | null
  present_value?: number | null
  shares_outstanding?: number | null
  source_refs?: string[] | null
}

export interface MonteCarloHistogramBin {
  lower_bound: number
  upper_bound: number
  count: number
  probability: number
}

export interface MonteCarloResults {
  bear_p10?: number | null
  base_p50?: number | null
  bull_p90?: number | null
  iteration_count?: number | null
  valid_sample_count?: number | null
  distribution?: "normal" | null
  random_seed?: number | null
  histogram_bins?: MonteCarloHistogramBin[]
  live_price_percentile?: number | null
}

export interface SensitivityMatrixRow {
  growth_rate: number
  cells: Array<{
    discount_rate: number
    fair_value: number | null
  }>
}

/** Matches the actual FastAPI /api/v1/valuation/dcf response. */
export interface DCFData {
  ticker: string;
  computed_fair_value?: number | null;
  margin_of_safety_percentage?: number;
  valuation_status: string;
  valuation_methodology: ValuationMethodology;
  engine_metadata: EngineMetadata;
  projections: ApiProjectionYear[];
  monte_carlo_results: MonteCarloResults;
  implied_expectations: Record<string, unknown>;
  underlying_assumptions: {
    fcf_0?: number;
    fcf_projections?: number[];
    revenue_projections?: Array<{
      year: number;
      revenue: number;
      growth_rate: number;
      ebit_margin: number;
      ebit: number;
      tax_rate: number;
      nopat: number;
      reinvestment_rate: number;
      reinvestment: number;
      free_cash_flow: number;
    }>;
    projections?: ApiProjectionYear[];
    terminal_value?: number;
    enterprise_value?: number;
    present_value_fcfe?: number;
    present_value_terminal_value?: number;
    equity_value?: number;
    computed_fair_value?: number;
    raw_computed_fair_value?: number;
    reported_fcf_0?: number;
    maintenance_capex?: number;
    target_debt?: number;
    target_cash?: number;
    total_debt?: number;
    cash?: number;
    shares_outstanding?: number;
    wacc?: number;
    wacc_basis?: string;
    discount_rate?: number;
    discount_rate_basis?: string;
    wacc_components?: {
      market_cap?: number;
      total_debt?: number;
      invested_capital?: number;
      weight_equity?: number;
      weight_debt?: number;
      risk_free_rate?: number;
      beta?: number;
      market_risk_premium?: number;
      cost_of_equity?: number;
      interest_expense?: number;
      cost_of_debt?: number;
      effective_tax_rate?: number;
      cost_of_debt_after_tax?: number;
      wacc?: number;
    };
    stage_1_growth_rate?: number;
    perpetual_growth_rate?: number;
    projection_years?: number;
    driver_model?: string;
    base_revenue?: number;
    ebit_margin?: number;
    effective_tax_rate?: number;
    reinvestment_rate?: number;
    market_cap?: number;
    beta?: number;
    risk_free_rate?: number;
    market_risk_premium?: number;
    cost_of_equity?: number;
    computational_warnings?: string[];
    valuation_methodology?: ValuationMethodology;
    engine_metadata?: EngineMetadata;
    telemetry?: ValuationTelemetry;
  };
  current_price: number | null;
  sotp_breakdown?: {
    status?: string;
    classification_profile?: string;
    segment_source?: string;
    warning?: string;
    segments?: Array<{
      name?: string;
      reported_revenue?: number | null;
      revenue_percentage?: number | null;
      currency?: string | null;
      period_end?: string | null;
      source?: string | null;
      filing_url?: string | null;
    }>;
  } | null;
  reverse_dcf_sotp?: {
    is_active: boolean;
    target_price: number | null;
    implied_growth_rate: number | null;
    total_ev?: number;
    net_cash?: number;
    years?: number;
    horizon_years?: number;
    high_growth_segment_name?: string;
    classification_profile?: string;
    segments: Array<{
      name: string;
      is_high_growth: boolean;
      ev_contribution: number;
      value: number;
      margin: number;
      implied_growth?: number;
    }>;
  };
  forward_dcf?: {
    valuation_status: string;
    fair_value: number | null;
    fcf_growth_rate: number | null;
    wacc: number | null;
    projections: ApiProjectionYear[];
    sensitivity_matrix: SensitivityMatrixRow[];
    sensitivity_basis?: {
      scenario: "base";
      center_growth_rate: number | null;
      center_discount_rate: number | null;
      discount_rate_driver: "current_wacc" | "cost_of_equity";
      center_fair_value: number | null;
      overview_fair_value: number | null;
      calculation_basis: string;
    };
    scenarios: Record<string, {
      projections: ApiProjectionYear[];
      harvest_start_year?: number | null;
    }>;
  };
}

export interface ValuationTelemetry {
  market_cap?: number;
  market_cap_source?: string;
  beta?: number;
  beta_source?: string;
  risk_free_rate?: number;
  risk_free_rate_source?: string;
  risk_free_rate_as_of?: string;
  market_risk_premium?: number;
  cost_of_equity?: number;
  cost_of_equity_basis?: string;
}

export function methodologyBadgeClasses(methodology?: string) {
  void methodology
  return "border border-[#294231] bg-[#0A0D0B] text-[#B7C5BC]"
}

export function isRegulatoryFcfe(data?: DCFData) {
  return data?.valuation_methodology === "Regulatory FCFE"
}

export function getProjectionCashFlows(data?: DCFData) {
  const projected = data?.projections?.map((item) =>
    item.unlevered_free_cash_flow ?? item.free_cash_flow_to_equity ?? null,
  ).filter((value): value is number => typeof value === "number" && Number.isFinite(value)) ?? []

  return projected.length ? projected : data?.underlying_assumptions?.fcf_projections ?? []
}

export function DCFCard({ data }: { data: DCFData }) {
  const { current_price, underlying_assumptions } = data;
  const projections = getProjectionCashFlows(data);
  // The top-level field is the public API's active-engine result. Nested
  // values are compatibility fallbacks and must never override that contract.
  const apiFairValue = [
    data.computed_fair_value,
    underlying_assumptions.computed_fair_value,
    data.forward_dcf?.fair_value,
  ].find((value): value is number => typeof value === "number" && Number.isFinite(value)) ?? null;
  const chartData = projections.map((value, index) => ({ y: index + 1, v: value }));
  const activeUpside = typeof data.margin_of_safety_percentage === "number" && Number.isFinite(data.margin_of_safety_percentage)
    ? data.margin_of_safety_percentage
    : null;
  const under = activeUpside === null ? null : activeUpside >= 0;
  const horizonSensitivity = data.engine_metadata?.consensus_horizon_sensitivity;
  const isConsensusSensitive = horizonSensitivity?.warning_triggered === true;

  return (
    <GlassCard>
      <CardHeading
        title="Discounted Cash Flow (DCF)"
        subtitle="Intrinsic value from projected free cash flow"
        tooltipText="Calculates intrinsic value from projected future free cash flows discounted to the present using the active model assumptions."
        icon={<LineChartIcon className="h-4 w-4" />}
        badge={
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-1 font-mono text-xs font-semibold tabular-nums ${
              under === null
                ? "border border-[#1A2E20] bg-[#111613] text-[#88998C]"
                : under
                ? "border border-[#00FF66]/30 bg-[#00FF66]/15 text-[#00FF66]"
                : "border border-amber-500/30 bg-amber-500/15 text-amber-400"
            }`}
          >
            {activeUpside === null
              ? "Margin unavailable"
              : isConsensusSensitive
              ? `${activeUpside > 0 ? "+" : ""}${activeUpside.toFixed(1)}% full-consensus margin`
              : `${under ? "+" : ""}${activeUpside.toFixed(1)}% ${under ? "Undervalued" : "Overvalued"}`}
          </span>
        }
      />
      <div className="p-5">
        {isConsensusSensitive ? (
          <section
            aria-labelledby="dcf-consensus-sensitivity-title"
            className="mb-5 rounded-lg border border-[#294231] bg-[#0A0D0B] p-4"
            data-testid="dcf-consensus-horizon-warning"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#294231] bg-[#111613] text-[#9AB0A1]">
                <Info className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <h3
                  id="dcf-consensus-sensitivity-title"
                  className="text-sm font-semibold text-[#E0E6E2]"
                >
                  Consensus-sensitive result
                </h3>
                <p className="mt-1 text-xs leading-5 text-[#9AB0A1]">
                  The primary result uses every valid provider consensus year. The comparison below is a diagnostic, not a replacement valuation.
                </p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-md border border-[#1A2E20] bg-[#111613] px-3 py-3">
                <p className="text-[11px] uppercase tracking-[0.1em] text-[#869E8F]">Full consensus</p>
                <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-[#E0E6E2]">
                  {typeof horizonSensitivity.full_fair_value === "number"
                    ? `$${fmt.money(horizonSensitivity.full_fair_value)}`
                    : "N/A"}
                </p>
                <p className="mt-1 text-[11px] text-[#869E8F]">Primary model result</p>
              </div>
              <div className="rounded-md border border-[#1A2E20] bg-[#111613] px-3 py-3">
                <p className="text-[11px] uppercase tracking-[0.1em] text-[#869E8F]">
                  Without {horizonSensitivity.removed_consensus_year ?? "last year"}
                </p>
                <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-[#E0E6E2]">
                  {typeof horizonSensitivity.truncated_fair_value === "number"
                    ? `$${fmt.money(horizonSensitivity.truncated_fair_value)}`
                    : "N/A"}
                </p>
                <p className="mt-1 text-[11px] text-[#869E8F]">Diagnostic only</p>
              </div>
            </div>
            <p className="mt-3 text-xs leading-5 text-[#9AB0A1]">
              Removing the {horizonSensitivity.removed_consensus_year ?? "last"} consensus year changes fair value
              {typeof horizonSensitivity.relative_delta_percentage === "number"
                ? ` by ${horizonSensitivity.relative_delta_percentage.toFixed(1)}%.`
                : " materially."}
              {typeof horizonSensitivity.last_consensus_revenue_growth_percentage === "number"
                ? ` That year assumes ${horizonSensitivity.last_consensus_revenue_growth_percentage.toFixed(1)}% revenue growth`
                : ""}
              {typeof horizonSensitivity.last_consensus_revenue_analyst_count === "number"
                ? ` across ${horizonSensitivity.last_consensus_revenue_analyst_count} revenue analysts.`
                : typeof horizonSensitivity.last_consensus_revenue_growth_percentage === "number"
                ? "."
                : ""}
            </p>
          </section>
        ) : null}
        <div className="grid grid-cols-5 gap-4">
          <div className="col-span-2">
            <p className="text-xs text-[#88998C]">
              {isConsensusSensitive ? "Full-consensus fair value" : "Fair Value"}
            </p>
            <p data-testid="dcf-fair-value" className="mt-1 font-mono text-3xl font-semibold tabular-nums text-white">
              {apiFairValue === null ? "N/A" : `$${fmt.money(apiFairValue)}`}
            </p>
            <p className="mt-1 font-mono text-xs tabular-nums text-[#88998C]">
              {current_price === null
                ? "Market reference unavailable"
                : `vs $${fmt.money(current_price)} market reference`}
            </p>
            <div className="mt-3 inline-flex items-center">
              <span className={`rounded-full px-3 py-1 text-xs font-mono ${methodologyBadgeClasses(data.valuation_methodology)}`}>
                {data.valuation_methodology}
              </span>
            </div>
          </div>
          <div className="col-span-3 h-20">
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 200, height: 80 }}>
              <AreaChart data={chartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="dcfFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00FF66" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#00FF66" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <Area
                  type="monotone"
                  dataKey="v"
                  stroke="#00FF66"
                  strokeWidth={2}
                  fill="url(#dcfFill)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="mt-5 grid gap-4 border-t border-[#1A2E20] pt-4">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#88998C]">Terminal Value</span>
            <span className="font-mono tabular-nums text-white">
              {typeof underlying_assumptions.terminal_value === "number"
                ? underlying_assumptions.terminal_value >= 1e9
                  ? fmt.bn(underlying_assumptions.terminal_value / 1e9, 1)
                  : underlying_assumptions.terminal_value >= 1e6
                    ? `$${(underlying_assumptions.terminal_value / 1e6).toFixed(1)}M`
                    : `$${fmt.money(underlying_assumptions.terminal_value, 1)}`
                : "N/A"}
            </span>
          </div>
        </div>
      </div>
    </GlassCard>
  )
}
