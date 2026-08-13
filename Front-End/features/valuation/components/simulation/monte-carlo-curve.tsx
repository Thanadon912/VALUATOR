"use client"

import { useEffect, useState } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Activity } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"
import type { DCFData } from "../DCFCard"

export function MonteCarloCurve({
  data,
  isUpdating = false,
  onRetry,
}: {
  data: DCFData
  isUpdating?: boolean
  onRetry?: () => void
}) {
  const [compactChart, setCompactChart] = useState(false)
  const mc = data.monte_carlo_results
  const livePrice = data.current_price
  const bins = mc?.histogram_bins ?? []
  const p10 = mc?.bear_p10
  const p50 = mc?.base_p50
  const p90 = mc?.bull_p90
  const warning = data.underlying_assumptions.computational_warnings
    ?.find((item) => item.toLowerCase().includes("monte carlo"))

  useEffect(() => {
    const media = window.matchMedia("(max-width: 639px)")
    const update = () => setCompactChart(media.matches)
    update()
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])

  if (
    typeof p10 !== "number" ||
    typeof p50 !== "number" ||
    typeof p90 !== "number"
  ) {
    return (
      <GlassCard aria-busy={isUpdating}>
        <CardHeading
          title="Probabilistic Valuation Range (Monte Carlo)"
          subtitle={isUpdating ? "Updating simulation outcomes" : "Simulation outcomes are unavailable"}
          icon={<Activity className="h-4 w-4" />}
        />
        <div className="p-5">
          {isUpdating ? (
            <div role="status" className="space-y-3">
              <p className="text-sm text-[#C8D4CC]">Running the 10,000-outcome simulation for the active assumptions…</p>
              <div className="h-28 animate-pulse rounded-sm bg-[#1A2E20]/60 motion-reduce:animate-none" />
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-[#294231] bg-[#0A0D0B] p-4">
              <div>
                <p className="text-sm font-semibold text-[#E0E6E2]">No simulation percentiles were returned</p>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-[#9AB0A1]">
                  {warning ?? "The valuation remains available, but the probabilistic layer did not return P10, P50, and P90 outcomes. No substitute values were created."}
                </p>
              </div>
              {onRetry ? (
                <button type="button" onClick={onRetry} className="min-h-11 rounded-sm border border-[#294231] px-4 text-sm font-semibold text-[#E0E6E2] hover:bg-[#1A2E20]">
                  Retry simulation
                </button>
              ) : null}
            </div>
          )}
        </div>
      </GlassCard>
    )
  }

  const chartData = bins.map((bin) => ({
    price: (bin.lower_bound + bin.upper_bound) / 2,
    probability: bin.probability * 100,
    range: `$${fmt.money(bin.lower_bound)}–$${fmt.money(bin.upper_bound)}`,
    count: bin.count,
  }))
  const percentiles = [
    {
      key: "P10",
      label: "10th percentile",
      description: "10% of valid simulations finish at or below this value",
      value: p10,
      color: "rgb(245 158 11)",
    },
    {
      key: "P50",
      label: "Median",
      description: "Half of valid simulations finish at or below this value",
      value: p50,
      color: "rgb(52 211 153)",
    },
    {
      key: "P90",
      label: "90th percentile",
      description: "10% of valid simulations finish above this value",
      value: p90,
      color: "rgb(134 158 143)",
    },
  ]
  const validSamples = mc.valid_sample_count ?? 0
  const iterationCount = mc.iteration_count ?? 10_000

  if (bins.length === 0) {
    return (
      <GlassCard aria-busy={isUpdating}>
        <CardHeading
          title="Probabilistic Valuation Range (Monte Carlo)"
          subtitle={`${validSamples.toLocaleString()} valid outcomes from ${iterationCount.toLocaleString()} runs`}
          icon={<Activity className="h-4 w-4" />}
        />
        {isUpdating ? (
          <p role="status" className="border-b border-[#1A2E20] px-5 py-2 text-xs text-amber-300">
            Updating for the active assumptions. The last complete percentiles remain visible.
          </p>
        ) : null}
        <div className="p-5">
          <div className="grid gap-3 md:grid-cols-3">
            {percentiles.map((percentile) => (
              <div key={percentile.key} className="rounded-md border border-[#1A2E20] bg-[#090A0B] px-4 py-3">
                <p className="text-xs text-[#869E8F]">{percentile.label}</p>
                <p className="mt-1.5 font-mono text-2xl font-semibold tabular-nums text-[#E0E6E2]">
                  ${fmt.money(percentile.value)}
                </p>
                <p className="mt-1 text-xs leading-5 text-[#869E8F]">{percentile.description}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#294231] px-4 py-3">
            <p className="text-xs leading-5 text-[#9AB0A1]">
              The percentile results are available, but the histogram bins were not returned, so no distribution chart is plotted.
            </p>
            {onRetry ? (
              <button type="button" onClick={onRetry} className="min-h-11 rounded-sm border border-[#294231] px-4 text-sm font-semibold text-[#E0E6E2] hover:bg-[#1A2E20]">
                Retry histogram
              </button>
            ) : null}
          </div>
        </div>
      </GlassCard>
    )
  }
  const chartMin = Math.min(...bins.map((bin) => bin.lower_bound))
  const chartMax = Math.max(...bins.map((bin) => bin.upper_bound))
  const safeLivePrice = typeof livePrice === "number" && Number.isFinite(livePrice) && livePrice > 0 ? livePrice : null
  const livePriceInRange = safeLivePrice !== null && safeLivePrice >= chartMin && safeLivePrice <= chartMax
  const livePricePosition = safeLivePrice !== null && safeLivePrice > chartMax
    ? "above"
    : safeLivePrice !== null && safeLivePrice < chartMin
      ? "below"
      : "within"
  const rangeComparison = safeLivePrice !== null && safeLivePrice > chartMax && chartMax > 0
    ? `${(safeLivePrice / chartMax).toFixed(2)}× the simulated upper bound`
    : safeLivePrice !== null && safeLivePrice < chartMin
      ? `${(chartMin / safeLivePrice).toFixed(2)}× below the simulated lower bound`
      : null

  return (
    <GlassCard aria-busy={isUpdating}>
      <CardHeading
        title="Probabilistic Valuation Range (Monte Carlo)"
        subtitle={`${validSamples.toLocaleString()} valid outcomes from ${iterationCount.toLocaleString()} runs · normal input perturbations`}
        icon={<Activity className="h-4 w-4" />}
      />
      {isUpdating ? (
        <p role="status" className="border-b border-[#1A2E20] px-5 py-2 text-xs text-amber-300">
          Updating for the active assumptions. The last complete simulation remains visible.
        </p>
      ) : null}
      <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="min-w-0">
        <div
          className="h-72 min-h-[288px] w-full min-w-0"
          role="img"
          aria-label={`Histogram of ${validSamples.toLocaleString()} valid simulated fair values from ${fmt.money(chartMin)} to ${fmt.money(chartMax)} dollars per share. The 10th percentile is ${fmt.money(p10)}, the median is ${fmt.money(p50)}, and the 90th percentile is ${fmt.money(p90)} dollars.${safeLivePrice !== null ? ` The live price of ${fmt.money(safeLivePrice)} dollars is ${livePricePosition} the simulated range.` : " The live price is unavailable."}`}
        >
          <ResponsiveContainer
            width="100%"
            height="100%"
            minWidth={1}
            minHeight={1}
            initialDimension={{ width: 680, height: 288 }}
          >
            <BarChart data={chartData} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(30 41 59 / 0.5)" vertical={false} />
              <XAxis
                dataKey="price"
                type="number"
                domain={["dataMin", "dataMax"]}
                tick={{ fill: "rgb(148 163 184)", fontSize: 11 }}
                axisLine={{ stroke: "rgb(30 41 59)" }}
                tickLine={false}
                tickFormatter={(value) => `$${Number(value).toFixed(0)}`}
              />
              <YAxis
                tick={{ fill: "rgb(148 163 184)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `${Number(value).toFixed(0)}%`}
                width={38}
              />
              <Tooltip
                cursor={{ fill: "rgb(134 158 143 / 0.08)" }}
                contentStyle={{
                  background: "#090A0B",
                  border: "1px solid rgba(16, 185, 129, 0.2)",
                  borderRadius: 6,
                  fontSize: 12,
                }}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.range ?? "Simulation range"}
                formatter={(value, name, item) => {
                  if (name === "probability") {
                    return [`${Number(value).toFixed(2)}% (${item.payload.count} outcomes)`, "Probability mass"]
                  }
                  return [String(value), String(name)]
                }}
              />
              <Bar dataKey="probability" fill="rgb(52 211 153)" fillOpacity={0.7} isAnimationActive={false} />
              {percentiles.map((percentile) => (
                <ReferenceLine
                  key={percentile.key}
                  x={percentile.value}
                  stroke={percentile.color}
                  strokeDasharray="5 4"
                  strokeWidth={1.5}
                  label={compactChart ? undefined : {
                    value: percentile.key,
                    position: "top",
                    fill: percentile.color,
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                />
              ))}
              {livePriceInRange ? (
                <ReferenceLine
                  x={safeLivePrice ?? undefined}
                  stroke="rgb(245 158 11)"
                  strokeWidth={2}
                  label={{
                    value: `LIVE $${safeLivePrice?.toFixed(2)}`,
                    position: "insideTopRight",
                    fill: "rgb(251 191 36)",
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                />
              ) : null}
            </BarChart>
          </ResponsiveContainer>
        </div>
        {safeLivePrice !== null && !livePriceInRange ? (
          <div role="status" className="mt-3 rounded-md border border-[#294231] bg-[#0A0D0B] px-4 py-3">
            <p className="text-xs font-semibold text-[#A9C6B3]">Live price is outside the displayed simulation range</p>
            <p className="mt-1 text-sm leading-6 text-[#E0E6E2]">
              <span className="font-mono font-semibold tabular-nums">${fmt.money(safeLivePrice)}</span>
              {livePricePosition === "above" ? " is above " : " is below "}
              the simulated range of <span className="font-mono tabular-nums">${fmt.money(chartMin)}–${fmt.money(chartMax)}</span>
              {rangeComparison ? ` · ${rangeComparison}.` : "."}
            </p>
          </div>
        ) : null}
        </div>

        <div className="flex flex-col justify-center gap-3">
          {percentiles.map((percentile) => (
            <div
              key={percentile.key}
              className="rounded-md border border-[#1A2E20] bg-[#090A0B] px-4 py-3"
            >
              <div className="flex items-center gap-2 text-xs text-[#869E8F]">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: percentile.color }} />
                {percentile.label}
              </div>
              <p className="mt-1.5 font-mono text-2xl font-semibold tabular-nums text-[#E0E6E2]">
                ${fmt.money(percentile.value)}
              </p>
              <p className="mt-1 text-xs leading-5 text-[#869E8F]">{percentile.description}</p>
            </div>
          ))}

          <div className="mt-1 rounded-md border border-amber-500/30 bg-amber-500/5 px-4 py-3">
            <p className="text-xs font-medium text-amber-400">Live market price</p>
            <p className="mt-1 text-sm leading-relaxed text-[#E0E6E2]">
              {safeLivePrice !== null ? (
                <>
                  <span className="font-mono font-semibold tabular-nums text-amber-300">
                    ${fmt.money(safeLivePrice)}
                  </span>
                  {typeof mc.live_price_percentile === "number"
                    ? ` is at the ${mc.live_price_percentile.toFixed(1)}th empirical percentile of valid simulations.`
                    : " percentile is unavailable because a live price was not included in the simulation response."}
                </>
              ) : "Unavailable because no sourced market price was returned."}
            </p>
          </div>
        </div>
      </div>
    </GlassCard>
  )
}
