"use client"

import { CircleSlash2, Coins } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"

/** Matches the actual FastAPI /api/v1/valuation/ddm response. */
export interface DDMData {
  ticker: string;
  computed_fair_value: number | null;
  margin_of_safety_percentage: number;
  valuation_status: string;
  underlying_assumptions: {
    status?: string;
    annual_dividend_per_share?: number;
    dividend_growth_cagr?: number;
    cost_of_equity?: number;
    payout_ratio?: number;
    computed_fair_value?: number | null;
    is_ddm_applicable?: boolean;
    dividend_yield?: number | null;
    applicability_reasons?: string[];
  };
  current_price: number;
}

export function DDMCard({ data }: { data: DDMData }) {
  const isDdmApplicable = data.underlying_assumptions.is_ddm_applicable;
  const isInapplicable =
    data.valuation_status === "INAPPLICABLE" ||
    data.underlying_assumptions.status === "DDM_INAPPLICABLE" ||
    isDdmApplicable === false;

  const payoutRatio = data.underlying_assumptions.payout_ratio;
  const upside = data.margin_of_safety_percentage;
  const dps = data.underlying_assumptions.annual_dividend_per_share;
  const dgr = data.underlying_assumptions.dividend_growth_cagr;
  const ke = data.underlying_assumptions.cost_of_equity;
  const dividendYield = data.underlying_assumptions.dividend_yield;
  const fairValue = data.computed_fair_value;
  const reasons = data.underlying_assumptions.applicability_reasons ?? [];

  const money = (value: number | null | undefined) =>
    typeof value === "number" && Number.isFinite(value) ? `$${fmt.money(value)}` : "N/A";
  const percent = (value: number | null | undefined, decimalInput = false) =>
    typeof value === "number" && Number.isFinite(value)
      ? fmt.pct(decimalInput ? value * 100 : value)
      : "N/A";

  return (
    <GlassCard className="relative overflow-hidden">
      <CardHeading
        title="Dividend Discount Model (DDM)"
        subtitle="Gordon growth on distributed cash"
        tooltipText="Estimates intrinsic value based on the present value of expected future dividend payments."
        icon={<Coins className="h-4 w-4" />}
        badge={
          <span className="rounded-md border border-[#1A2E20] bg-[#111613] px-2 py-1 font-mono text-xs tabular-nums text-white">
            Value {isInapplicable ? "N/A" : money(fairValue)}
          </span>
        }
      />
      {isInapplicable ? (
        <div className="p-5">
          <div className="flex items-start gap-3 rounded-md border border-[#294231] bg-[#0A0D0B] p-4">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[#294231] text-[#A9C6B3]">
              <CircleSlash2 className="h-4 w-4" />
            </span>
            <div>
              <p className="text-sm font-semibold text-[#E0E6E2]">DDM not applicable</p>
              <p className="mt-1 text-xs leading-5 text-[#88998C]">
                {reasons.length ? reasons.join(" ") : "The sourced dividend profile does not satisfy the DDM applicability rules."}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid gap-px bg-[#1A2E20] sm:grid-cols-2">
          <DdmMetric label="Annual Dividend / Share" value={money(dps)} />
          <DdmMetric label="Dividend Growth CAGR" value={percent(dgr, true)} />
          <DdmMetric label="Cost of Equity" value={percent(ke, true)} />
          <DdmMetric label="Dividend Payout Ratio" value={percent(payoutRatio)} />
          <DdmMetric label="Dividend Yield" value={percent(dividendYield, true)} />
          <DdmMetric
            label="Margin of Safety"
            value={typeof upside === "number" && Number.isFinite(upside) ? `${upside >= 0 ? "+" : ""}${upside.toFixed(1)}%` : "N/A"}
            accent={typeof upside === "number" ? upside >= 0 : undefined}
          />
        </div>
      )}
    </GlassCard>
  )
}

function DdmMetric({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 bg-[#090A0B] px-4 py-3">
      <span className="text-xs text-[#88998C]">{label}</span>
      <span className={`font-mono text-sm font-medium tabular-nums ${
          accent === undefined ? "text-white" : accent ? "text-[#00FF66]" : "text-amber-400"
        }`}>
        {value}
      </span>
    </div>
  )
}
