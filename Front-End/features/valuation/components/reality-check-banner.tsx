"use client"

import { Gauge } from "lucide-react"
import { fmt } from "@/lib/valuation"

type ValuationSegment = {
  name: string;
  is_high_growth: boolean;
  ev_contribution: number;
  margin: number;
  implied_growth?: number;
};

type ValuationPayload = {
  ticker?: string;
  market_price?: number;
  current_price?: number | null;
  calculated_price?: number;
  total_ev?: number;
  net_cash?: number;
  required_cagr?: number;
  years?: number;
  segments?: ValuationSegment[];
  implied_expectations?: {
    implied_revenue_cagr?: number | null;
    implied_stage_1_revenue_cagr?: number | null;
    implied_operating_margin?: number | null;
    implied_target_ebit_margin?: number | null;
  };
};

function resolveRealityExpectations(data: ValuationPayload) {
  const highGrowthSegment = data?.segments?.find(segment => segment.is_high_growth)
  if (typeof data?.required_cagr === "number" && Number.isFinite(data.required_cagr) && highGrowthSegment) {
    return {
      requiredCagr: data.required_cagr,
      margin: highGrowthSegment.margin,
      subject: highGrowthSegment.name,
    }
  }

  const impliedGrowth = data?.implied_expectations?.implied_stage_1_revenue_cagr
    ?? data?.implied_expectations?.implied_revenue_cagr
  const impliedMargin = data?.implied_expectations?.implied_target_ebit_margin
    ?? data?.implied_expectations?.implied_operating_margin
  if (typeof impliedGrowth === "number" && Number.isFinite(impliedGrowth)) {
    return {
      requiredCagr: impliedGrowth * 100,
      margin: typeof impliedMargin === "number" && Number.isFinite(impliedMargin)
        ? impliedMargin * 100
        : null,
      subject: data?.ticker ? `${data.ticker} whole company` : "whole company",
    }
  }

  return null
}

export function RealityCheckBanner({ data }: { data: ValuationPayload }) {
  const marketPrice = data?.market_price ?? data?.current_price ?? null;
  const resolved = resolveRealityExpectations(data)
  const horizonYears = data?.years ?? 10;

  if (!resolved || typeof marketPrice !== "number" || !Number.isFinite(marketPrice) || marketPrice <= 0) return null;

  const { requiredCagr, margin, subject } = resolved

  return (
    <div className="relative overflow-hidden rounded-xl border border-amber-500/30 bg-amber-500/5">

      <div className="relative flex flex-col gap-4 p-5 md:flex-row md:items-center md:gap-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-400">
            <Gauge className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-400">
              Market-implied expectations
            </p>
            <p className="mt-0.5 text-sm font-semibold text-[#E0E6E2]">Implied Market Expectations</p>
          </div>
        </div>

        <div className="hidden h-12 w-px bg-amber-500/20 md:block" />

        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-[#E0E6E2]">
            To justify the current live price of{" "}
            <span className="font-mono font-semibold tabular-nums text-[#E0E6E2]">
              ${fmt.money(marketPrice)}
            </span>
            , this company must achieve a{" "}
            <span className="font-mono font-semibold tabular-nums text-amber-300">
              {fmt.pct(requiredCagr, 1)} Revenue CAGR
            </span>{" "}
            {margin !== null ? <>and sustain operating margins for {subject} at{" "}
              <span className="font-mono font-semibold tabular-nums text-amber-300">
                {fmt.pct(margin, 1)}
              </span>{" "}</> : null}
            for the next {horizonYears} years.
          </p>
          <p className="mt-2 text-sm font-medium text-amber-200/90">
            Review whether these model-implied requirements are supported by the available evidence; they are not a forecast.
          </p>
        </div>
      </div>
    </div>
  )
}
