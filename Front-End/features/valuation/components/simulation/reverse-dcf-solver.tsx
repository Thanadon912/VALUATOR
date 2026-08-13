"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { RotateCcw, Target } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"

type ValuationSegment = {
  name: string;
  is_high_growth: boolean;
  ev_contribution: number;
  value: number;
  margin: number;
  implied_growth?: number;
};

type SotpBreakdown = Record<string, unknown>;

type FeasiblePoint = {
  growth: number;
  margin: number;
  model_value: number;
  gap: number;
  distance: number;
};

type ImpliedExpectations = {
  solver_status?: string;
  implied_revenue_cagr?: number;
  implied_stage_1_revenue_cagr?: number;
  implied_operating_margin?: number;
  implied_target_ebit_margin?: number;
  implied_terminal_revenue_growth?: number | null;
  implied_terminal_ebit_margin?: number | null;
  implied_year_n_revenue?: number | null;
  implied_year_n_fcff?: number | null;
  implied_projection_horizon_years?: number;
  target_price?: number;
  model_fair_value?: number;
  feasible_curve?: FeasiblePoint[];
};

type ValuationPayload = {
  ticker?: string;
  market_price?: number;
  current_price?: number | null;
  target_price?: number;
  computed_fair_value?: number | null;
  sotp_breakdown?: SotpBreakdown | null;
  implied_expectations?: ImpliedExpectations;
  segments?: ValuationSegment[];
  required_cagr?: number;
  underlying_assumptions?: {
    computational_warnings?: string[];
    stage_1_growth_rate?: number;
    perpetual_growth_rate?: number;
    discount_rate?: number;
    wacc?: number;
    cost_of_equity?: number;
  };
  reverse_dcf_sotp?: {
    is_active?: boolean;
    solver_available?: boolean;
    requested_target_price?: number | null;
    model_fair_value?: number | null;
    target_price?: number | null;
    implied_growth_rate?: number | null;
    segments?: ValuationSegment[];
  };
};

function narrative(price: number, cagr: number, margin: number, segmentName: string) {
  return `At a $${price.toFixed(2)} target, the model implies ${cagr.toFixed(1)}% revenue CAGR and ${margin.toFixed(1)}% operating margin for ${segmentName}. This is a model requirement, not a forecast.`
}

function Metric({
  label,
  value,
  suffix,
}: {
  label: string
  value: number
  suffix: string
}) {
  return (
    <div className="rounded-md border border-emerald-900/20 bg-[#090A0B] px-5 py-4">
      <p className="text-xs text-[#869E8F]">{label}</p>
      <div className="mt-1 flex items-baseline gap-1">
        <motion.span
          key={value.toFixed(1)}
          initial={{ opacity: 0.4, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="font-mono text-4xl font-bold tabular-nums text-emerald-400"
        >
          {value.toFixed(1)}
        </motion.span>
        <span className="font-mono text-2xl font-semibold text-emerald-400/70">{suffix}</span>
      </div>
    </div>
  )
}

/**
 * Resolve implied expectations from two possible data paths:
 *   1. SOTP tickers: fields live inside data.sotp_breakdown
 *   2. Standard DCF tickers: fields live inside data.implied_expectations
 */
function resolveExpectations(
  data: ValuationPayload,
): {
  cagr: number
  margin: number
  segmentName: string
  curve?: FeasiblePoint[]
  terminalGrowth?: number | null
  terminalMargin?: number | null
  horizonYears?: number
} | null {
  // Path 1 — SOTP breakdown (has per-segment detail)
  if (data?.required_cagr !== undefined && data?.segments && data.segments.length > 0) {
    const hg = data.segments.find((s: ValuationSegment) => s.is_high_growth)
    if (hg) {
      return {
        cagr: data.required_cagr,
        margin: hg.margin,
        segmentName: hg.name,
      }
    }
  }

  // Path 2 — Standard DCF implied expectations (no segments, whole-company)
  const ie = data?.implied_expectations
  const stageGrowth = ie?.implied_stage_1_revenue_cagr ?? ie?.implied_revenue_cagr
  const targetMargin = ie?.implied_target_ebit_margin ?? ie?.implied_operating_margin
  if (typeof stageGrowth === "number" && Number.isFinite(stageGrowth)) {
    return {
      cagr: stageGrowth * 100,
      margin: (targetMargin ?? 0) * 100,
      segmentName: data?.ticker ? `${data.ticker} Whole Company` : "Whole Company",
      curve: ie?.feasible_curve,
      terminalGrowth: ie?.implied_terminal_revenue_growth,
      terminalMargin: ie?.implied_terminal_ebit_margin,
      horizonYears: ie?.implied_projection_horizon_years,
    }
  }

  return null
}

function nearestSolvedScenarioIndex(
  curve: FeasiblePoint[] | undefined,
  solvedCagrPercent: number | undefined,
  solvedMarginPercent: number | undefined,
) {
  if (!curve?.length || solvedCagrPercent === undefined || solvedMarginPercent === undefined) return 0

  return curve.reduce((nearestIndex, point, index) => {
    const distance = Math.hypot(
      point.growth * 100 - solvedCagrPercent,
      point.margin * 100 - solvedMarginPercent,
    )
    const nearest = curve[nearestIndex]
    const nearestDistance = Math.hypot(
      nearest.growth * 100 - solvedCagrPercent,
      nearest.margin * 100 - solvedMarginPercent,
    )
    return distance < nearestDistance ? index : nearestIndex
  }, 0)
}

function targetMatches(responseTarget: number | null | undefined, requestedTarget: number) {
  return typeof responseTarget === "number" &&
    Number.isFinite(responseTarget) &&
    Math.abs(responseTarget - requestedTarget) <= 0.01
}

export function ReverseDcfSolver({ data }: { data: ValuationPayload }) {
  const marketPrice = data?.market_price ?? data?.current_price ?? null;
  const ticker = data.ticker ?? ""
  const assumptionContextKey = [
    ticker,
    data.underlying_assumptions?.stage_1_growth_rate,
    data.underlying_assumptions?.perpetual_growth_rate,
    data.underlying_assumptions?.discount_rate ?? data.underlying_assumptions?.wacc ?? data.underlying_assumptions?.cost_of_equity,
  ].join(":")
  const [solverResult, setSolverResult] = useState<{
    ticker: string
    contextKey: string
    requestedTarget: number
    data: ValuationPayload
  } | null>(null)
  const [targetState, setTargetState] = useState<{
    ticker: string
    contextKey: string
    value: string
  } | null>(null)
  const [isSolving, setIsSolving] = useState(false)
  const [solveError, setSolveError] = useState<string | null>(null)
  const solverMatchesContext = solverResult?.ticker === ticker && solverResult.contextKey === assumptionContextKey
  const targetMatchesContext = targetState?.ticker === ticker && targetState.contextKey === assumptionContextKey
  const activeData = solverMatchesContext ? solverResult.data : data
  const targetText = targetMatchesContext
    ? targetState.value
    : typeof marketPrice === "number" && Number.isFinite(marketPrice)
      ? marketPrice.toFixed(2)
      : ""
  const targetPrice = Number(targetText)
  const targetValid = targetText.trim() !== "" && Number.isFinite(targetPrice) && targetPrice > 0
  const resolved = resolveExpectations(activeData)
  const solverWarning = activeData?.underlying_assumptions?.computational_warnings
    ?.find(warning => warning.startsWith("Implied expectations unavailable:"))

  // If we have a feasible curve, we scrub through its valid mathematical scenarios.
  // Otherwise, we fallback to the legacy price-extrapolation slider for SOTP.
  const hasCurve = resolved?.curve && resolved.curve.length > 1
  const defaultIndex = nearestSolvedScenarioIndex(
    resolved?.curve,
    resolved?.cagr,
    resolved?.margin,
  )

  const scenarioKey = [
    assumptionContextKey,
    resolved?.cagr,
    resolved?.margin,
    activeData.target_price ?? activeData.implied_expectations?.target_price,
    resolved?.curve?.length,
  ].join(":")
  const [scenarioState, setScenarioState] = useState<{ key: string; index: number } | null>(null)
  const scenarioIndex = scenarioState?.key === scenarioKey ? scenarioState.index : defaultIndex

  const solveTarget = async () => {
    if (!ticker || !targetValid) return
    const requestedTarget = targetPrice
    const assumptions = data.underlying_assumptions
    const params = new URLSearchParams({
      ticker,
      implied_target_price: String(requestedTarget),
    })
    const growth = assumptions?.stage_1_growth_rate
    const perpetualGrowth = assumptions?.perpetual_growth_rate
    const discountRate = assumptions?.discount_rate ?? assumptions?.wacc ?? assumptions?.cost_of_equity
    if (typeof growth === "number") params.set("stage_1_growth_rate", String(growth))
    if (typeof perpetualGrowth === "number") params.set("perpetual_growth_rate", String(perpetualGrowth))
    if (typeof discountRate === "number") params.set("discount_rate", String(discountRate))

    setIsSolving(true)
    setSolveError(null)
    try {
      const response = await fetch(`/api/v1/valuation/dcf?${params.toString()}`, {
        signal: AbortSignal.timeout(90_000),
      })
      if (!response.ok) throw new Error(`Target solver request failed (${response.status})`)
      const payload = await response.json() as ValuationPayload
      const reverse = payload.reverse_dcf_sotp
      const standardTarget = payload.implied_expectations?.target_price
      const standardConverged = payload.implied_expectations?.solver_status === "converged" &&
        targetMatches(standardTarget, requestedTarget) &&
        resolveExpectations(payload) !== null
      const sotpEligible = reverse?.is_active === true &&
        reverse.solver_available === true &&
        targetMatches(reverse.requested_target_price, requestedTarget) &&
        typeof reverse.implied_growth_rate === "number" &&
        reverse.segments?.some((segment) => segment.is_high_growth)
      const accepted = standardConverged
        ? payload
        : sotpEligible
          ? {
              ...payload,
              ...reverse,
              target_price: reverse.requested_target_price ?? undefined,
              required_cagr: reverse.implied_growth_rate ?? undefined,
              segments: reverse.segments ?? [],
            }
          : null
      if (!accepted || !resolveExpectations(accepted)) {
        const warning = payload.underlying_assumptions?.computational_warnings?.find((item) =>
          item.startsWith("Implied expectations unavailable:"),
        )
        if (
          payload.implied_expectations?.solver_status === "converged" &&
          typeof standardTarget === "number" &&
          !targetMatches(standardTarget, requestedTarget)
        ) {
          throw new Error("The solver response did not match the requested target. The previous result was kept.")
        }
        if (warning) throw new Error(`${warning} Try a target closer to the current market price.`)
        if (reverse?.is_active && reverse.solver_available === false) {
          throw new Error("This company's segment solver is unavailable. The whole-company solver also could not reach this target.")
        }
        throw new Error("The solver did not return a converged result for this exact target. Try a target closer to the current market price.")
      }
      setSolverResult({
        ticker,
        contextKey: assumptionContextKey,
        requestedTarget,
        data: accepted,
      })
      setTargetState({
        ticker,
        contextKey: assumptionContextKey,
        value: requestedTarget.toFixed(2),
      })
    } catch (error) {
      setSolveError(error instanceof Error ? error.message : "Target solver request failed")
    } finally {
      setIsSolving(false)
    }
  }

  const resetToLive = () => {
    if (typeof marketPrice !== "number" || !Number.isFinite(marketPrice) || marketPrice <= 0) return
    setTargetState({ ticker, contextKey: assumptionContextKey, value: marketPrice.toFixed(2) })
    setSolverResult(null)
    setScenarioState(null)
    setSolveError(null)
  }

  if (!resolved || typeof marketPrice !== "number" || !Number.isFinite(marketPrice) || marketPrice <= 0) {
    return (
      <GlassCard>
        <CardHeading
          title="Market Expectations Solver (Reverse DCF)"
          subtitle="Goal-seek the growth & margin baked into any target price"
          icon={<Target className="h-4 w-4" />}
          tooltipText="Reverse-engineers the DCF formula from the live price to determine the implied growth and margin expectations priced in by the market."
        />
        <div className="p-5">
          <div className="rounded-md border border-[#294231] bg-[#0A0D0B] px-5 py-4">
            <p className="text-sm font-semibold text-[#DCEBE2]">Market-implied expectations are unavailable</p>
            <p className="mt-1 text-sm leading-relaxed text-[#A9BAAF]">
              {solverWarning ?? "Implied market expectations are unavailable for the current sourced inputs and solver bounds."}
            </p>
          </div>
        </div>
      </GlassCard>
    )
  }

  const safeTargetPrice = targetValid
    ? targetPrice
    : marketPrice
  const {
    cagr: baseCagr,
    margin: baseMargin,
    segmentName,
    curve,
    terminalGrowth,
    terminalMargin,
    horizonYears,
  } = resolved

  let impliedCagr = baseCagr
  let impliedMargin = baseMargin
  let displayPrice = marketPrice
  let sliderMin = 0
  let sliderMax = 0
  let sliderVal = 0
  let pct = 0

  if (hasCurve && curve) {
    sliderMin = 0
    sliderMax = curve.length - 1
    sliderVal = scenarioIndex
    pct = sliderMax > 0 ? (sliderVal / sliderMax) * 100 : 50
    
    const safeScenarioIndex = Math.min(scenarioIndex, curve.length - 1)
    const point = curve[safeScenarioIndex]
    impliedCagr = point.growth * 100
    impliedMargin = point.margin * 100
    displayPrice = point.model_value
  } else {
    displayPrice = activeData.target_price ?? activeData.implied_expectations?.target_price ?? marketPrice
  }

  const solvedTarget = activeData.implied_expectations?.target_price ?? activeData.target_price ?? marketPrice
  const targetDirty = targetValid && typeof solvedTarget === "number"
    ? Math.abs(targetPrice - solvedTarget) > 0.01
    : targetText.trim() !== ""

  return (
    <GlassCard aria-busy={isSolving}>
      <CardHeading
        title="Market Expectations Solver (Reverse DCF)"
        subtitle="Goal-seek the growth & margin baked into any target price"
        icon={<Target className="h-4 w-4" />}
        tooltipText="Reverse-engineers the DCF formula from the live price to determine the implied growth and margin expectations priced in by the market."
      />
      <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-2">
        {/* Slider control */}
        <div className="flex flex-col justify-center">
          <div className="mb-5 rounded-md border border-[#1A2E20] bg-[#090A0B] p-4">
            <label className="text-xs text-[#869E8F]" htmlFor="reverse-dcf-target-price">
              Target price to solve
            </label>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
              <div className="relative min-w-0">
                <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center font-mono text-sm text-[#869E8F]">$</span>
                <input
                  id="reverse-dcf-target-price"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={targetText}
                  aria-invalid={!targetValid}
                  aria-describedby="reverse-dcf-target-help"
                  onChange={(event) => setTargetState({
                    ticker,
                    contextKey: assumptionContextKey,
                    value: event.target.value,
                  })}
                  className="h-11 w-full rounded-sm border border-[#294231] bg-[#0A0D0B] pl-7 pr-3 font-mono text-sm tabular-nums text-[#E0E6E2] outline-none focus:border-[#B7FF3C]"
                />
              </div>
              <button
                type="button"
                onClick={solveTarget}
                disabled={isSolving || !targetValid || !targetDirty}
                className="h-11 rounded-sm bg-[#B7FF3C] px-4 text-sm font-semibold text-[#071008] disabled:opacity-40"
              >
                {isSolving ? "Solving…" : solveError ? "Retry target" : "Solve target"}
              </button>
              <button
                type="button"
                onClick={resetToLive}
                className="inline-flex h-11 items-center gap-2 rounded-sm border border-[#294231] px-3 text-sm text-[#C8D4CC] hover:bg-[#1A2E20]"
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Reset to live
              </button>
            </div>
            <p id="reverse-dcf-target-help" className={`mt-2 text-xs ${!targetValid || solveError ? "text-amber-300" : "text-[#869E8F]"}`}>
              {!targetValid
                ? "Enter a target price greater than $0."
                : isSolving
                  ? `Solving the model for $${safeTargetPrice.toFixed(2)}. The last complete result remains visible.`
                  : targetDirty && typeof solvedTarget === "number"
                    ? `Results below still reflect $${solvedTarget.toFixed(2)}. Select Solve target to update them.`
                    : `Results below reflect the solved $${Number(solvedTarget ?? safeTargetPrice).toFixed(2)} target.`}
            </p>
            {solveError ? <p role="alert" className="mt-2 text-xs text-amber-300">{solveError}</p> : null}
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-xs text-[#869E8F]">
              {hasCurve ? "Market-Implied Valuation Price" : "Target Valuation Price"}
            </span>
            <div className="flex items-baseline gap-1">
              <span className="font-mono text-lg text-[#869E8F]">$</span>
              <span className="font-mono text-3xl font-bold tabular-nums text-[#E0E6E2]">
                {displayPrice.toFixed(2)}
              </span>
            </div>
          </div>

          {hasCurve ? <div className="relative mt-4">
            <div
              className="pointer-events-none absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full"
              style={{ background: `linear-gradient(to right, rgb(52 211 153) 0%, rgb(34 211 238) ${pct}%, rgb(30 41 59) ${pct}%, rgb(30 41 59) 100%)` }}
              aria-hidden="true"
            />
            <input
              type="range"
              min={sliderMin}
              max={sliderMax}
              step={1}
              value={sliderVal}
              onChange={(e) => setScenarioState({ key: scenarioKey, index: Number(e.target.value) })}
              aria-label="Explore feasible growth and margin pairs"
                className="mc-range h-11 w-full cursor-pointer appearance-none bg-transparent"
            />
            <div className="mt-2 flex justify-between font-mono text-[10px] tabular-nums text-[#869E8F]">
              <span>High Margin</span>
              <span>High Growth</span>
            </div>
          </div> : null}

          <p className="mt-6 text-sm leading-relaxed text-[#869E8F]">
            {narrative(displayPrice, impliedCagr, impliedMargin, segmentName)}
          </p>
        </div>

        {/* Solved expectations */}
        <div className="flex flex-col justify-center gap-4">
          <Metric label="Required Stage-1 Revenue Growth" value={impliedCagr} suffix="%" />
          <Metric label={`Required Target EBIT Margin (${segmentName})`} value={impliedMargin} suffix="%" />
          {terminalGrowth != null && terminalMargin != null ? (
            <p className="rounded-md border border-emerald-900/20 bg-[#090A0B] px-4 py-3 text-xs leading-5 text-[#869E8F]">
              The solved trajectory fades to {(terminalGrowth * 100).toFixed(1)}% terminal growth and {(terminalMargin * 100).toFixed(1)}% terminal EBIT margin{horizonYears ? ` after ${horizonYears} years` : ""}. Stage-1 requirements are not terminal assumptions.
            </p>
          ) : null}
        </div>
      </div>

      <style jsx>{`
        .mc-range::-webkit-slider-thumb {
          appearance: none;
          height: 22px;
          width: 22px;
          border-radius: 9999px;
          background: #0b0f17;
          border: 2px solid rgb(16 185 129);
          box-shadow: none;
          cursor: pointer;
          transition: transform 0.1s ease;
        }
        .mc-range::-webkit-slider-thumb:active {
          transform: scale(1.15);
        }
        .mc-range::-moz-range-thumb {
          height: 22px;
          width: 22px;
          border-radius: 9999px;
          background: #0b0f17;
          border: 2px solid rgb(16 185 129);
          box-shadow: none;
          cursor: pointer;
        }
      `}</style>
    </GlassCard>
  )
}
