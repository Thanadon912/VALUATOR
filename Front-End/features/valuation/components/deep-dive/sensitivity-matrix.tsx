import { Grid3x3 } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"
import type { DCFData } from "../DCFCard"
import { isRegulatoryFcfe } from "../DCFCard"

export function SensitivityMatrix({ 
  data,
  isUpdating = false,
  onRetry,
}: { 
  data?: DCFData;
  isUpdating?: boolean;
  onRetry?: () => void;
}) {
  const currentPrice = typeof data?.current_price === "number" && Number.isFinite(data.current_price)
    ? data.current_price
    : null;
  const matrix = data?.forward_dcf?.sensitivity_matrix ?? [];
  const discountRates = matrix[0]?.cells.map((cell) => cell.discount_rate) ?? [];
  const regulatoryFcfe = isRegulatoryFcfe(data);
  const baseGrowthIndex = Math.floor(matrix.length / 2);
  const baseDiscountIndex = Math.floor(discountRates.length / 2);
  const warning = data?.underlying_assumptions?.computational_warnings
    ?.find((item) => item.toLowerCase().includes("sensitivity"));

  if (matrix.length === 0) {
    return (
      <GlassCard aria-busy={isUpdating}>
        <CardHeading
          title="WACC Sensitivity Matrix"
          subtitle="Base-case sensitivity · center matches the Overview DCF"
          icon={<Grid3x3 className="h-4 w-4" />}
        />
        <div className="p-5">
          {isUpdating ? (
            <div role="status" className="space-y-3" aria-label="Updating sensitivity matrix">
              <p className="text-sm text-[#C8D4CC]">Updating the sensitivity matrix for the active assumptions…</p>
              <div className="h-24 animate-pulse rounded-sm bg-[#1A2E20]/60 motion-reduce:animate-none" />
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-[#294231] bg-[#0A0D0B] p-4">
              <div>
                <p className="text-sm font-semibold text-[#E0E6E2]">Sensitivity matrix unavailable</p>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-[#9AB0A1]">
                  {warning ?? "The backend did not return sensitivity rows for this completed model. No values were inferred."}
                </p>
              </div>
              {onRetry ? (
                <button type="button" onClick={onRetry} className="min-h-11 rounded-sm border border-[#294231] px-4 text-sm font-semibold text-[#E0E6E2] hover:bg-[#1A2E20]">
                  Retry valuation
                </button>
              ) : null}
            </div>
          )}
        </div>
      </GlassCard>
    )
  }

  const flat = matrix.flatMap((row) => row.cells.map((cell) => cell.fair_value)).filter((value): value is number => value !== null)
  const min = Math.min(...flat)
  const max = Math.max(...flat)

  // heat: green for values above live price, red below
  const cellStyle = (v: number | null) => {
    if (v === null) return { background: "rgba(134,158,143,0.05)", color: "rgb(134 158 143)" }
    const t = (v - min) / (max - min || 1)
    if (currentPrice === null) {
      return { background: `rgba(134,158,143,${0.06 + t * 0.12})`, color: "rgb(224 230 226)" }
    }
    const above = v >= currentPrice
    const alpha = 0.08 + t * 0.22
    return above
      ? { background: `rgba(16,185,129,${alpha})`, color: "rgb(167 243 208)" }
      : { background: `rgba(245,158,11,${0.28 - t * 0.18})`, color: "rgb(253 230 138)" }
  }

  return (
    <GlassCard aria-busy={isUpdating}>
      <CardHeading
        title="WACC Sensitivity Matrix"
        subtitle="Base-case sensitivity · center matches the Overview DCF"
        icon={<Grid3x3 className="h-4 w-4" />}
      />
      {isUpdating ? (
        <p role="status" className="border-b border-[#1A2E20] px-4 py-2 text-xs text-amber-300">
          Updating for the active assumptions. The last complete matrix remains visible.
        </p>
      ) : null}
      <p id="sensitivity-scroll-hint" className="px-4 pt-3 text-[11px] text-[#869E8F] sm:hidden">Swipe horizontally to compare discount rates.</p>
      <div className="relative">
      <div
        className="max-w-full overflow-x-auto overscroll-x-contain p-2 [scroll-padding-left:9rem] [scroll-snap-type:x_proximity] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#B7FF3C] sm:p-4 sm:[scroll-padding-left:12rem]"
        role="region"
        aria-label="Sensitivity matrix"
        aria-describedby="sensitivity-scroll-hint"
        tabIndex={matrix.length > 0 ? 0 : -1}
      >
        <table className="w-full min-w-[680px] table-fixed border-separate border-spacing-1 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-30 w-36 min-w-36 max-w-36 border-r border-[#294231] bg-[#090A0B] p-2 text-left text-xs text-[#869E8F] shadow-[12px_0_18px_-14px_rgba(183,255,60,0.55)] sm:w-48 sm:min-w-48 sm:max-w-48" data-testid="sensitivity-sticky-label">
                Stage-1 growth ↓ / {regulatoryFcfe ? "Ke" : "WACC"} →
              </th>
              {discountRates.map((w) => (
                <th
                  key={w}
                  className="min-w-[6.75rem] snap-start p-2 text-center font-mono text-xs tabular-nums text-[#869E8F]"
                >
                  {(w * 100).toFixed(2)}%
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, gi) => (
              <tr key={row.growth_rate}>
                <td className="sticky left-0 z-20 w-36 min-w-36 max-w-36 border-r border-[#294231] bg-[#090A0B] p-2 text-left font-mono text-xs tabular-nums text-[#869E8F] shadow-[12px_0_18px_-14px_rgba(183,255,60,0.55)] sm:w-48 sm:min-w-48 sm:max-w-48">
                  {(row.growth_rate * 100).toFixed(1)}%
                </td>
                {row.cells.map((cell, wi) => {
                  const isBase = gi === baseGrowthIndex && wi === baseDiscountIndex
                  return (
                    <td key={cell.discount_rate} className="min-w-[6.75rem] snap-start p-0">
                      <div
                        style={cellStyle(cell.fair_value)}
                        data-testid={isBase ? "sensitivity-base-cell" : undefined}
                        className={`flex h-9 items-center justify-center rounded-sm font-mono text-xs font-medium tabular-nums ${
                          isBase ? "ring-1 ring-emerald-500 bg-emerald-500/10" : ""
                        }`}
                      >
                        {cell.fair_value === null ? "N/A" : `$${fmt.money(cell.fair_value)}`}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-[#111613] to-transparent sm:hidden" aria-hidden="true" />
      </div>
      <p className="px-4 pb-4 text-[11px] leading-5 text-[#869E8F]">
        Each cell reruns the complete model with the displayed stage-1 growth and {regulatoryFcfe ? "Cost of Equity" : "current WACC"}; the center preserves all active Overview assumptions.
      </p>
    </GlassCard>
  )
}
