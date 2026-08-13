import { Table, TrendingDown, Minus, TrendingUp } from "lucide-react"
import { GlassCard } from "@/components/ui/glass-card"
import { scenarioMeta, fmt, type Scenario } from "@/lib/valuation"
import type { ApiProjectionYear, DCFData } from "../DCFCard"
import { isRegulatoryFcfe } from "../DCFCard"

export type ProjectionYear = {
  year: number
  primaryDriver: number
  growth: number | null
  nopat: number | null
  ebitMargin: number | null
  capitalDeduction: number
  cashFlow: number
  capitalDeductionLabel: string
  cashFlowLabel: string
}

export function dynamicScenarioProjection(scenario: Scenario, dcfData?: DCFData): ProjectionYear[] {
  const scenarioProjections = dcfData?.forward_dcf?.scenarios?.[scenario]?.projections
  
  const projections = scenarioProjections?.length 
    ? scenarioProjections 
    : dcfData?.projections?.length
      ? dcfData.projections
      : dcfData?.underlying_assumptions?.projections ?? []

  if (!projections.length) {
    return []
  }

  return projections.map((p: ApiProjectionYear) => {
    const primaryDriver = (p.revenue ?? p.net_income ?? 0)
    const growth = p.revenue_growth ?? p.net_income_growth ?? null
    const nopat = p.nopat != null ? p.nopat : null
    const capitalDeduction = (p.capital_deduction_value ?? 0)
    const baseCashFlow = p.unlevered_free_cash_flow ?? p.free_cash_flow_to_equity
    const cashFlow = baseCashFlow != null
      ? baseCashFlow
      : (nopat ?? primaryDriver) - capitalDeduction
    return {
      year: p.year,
      primaryDriver,
      growth,
      nopat,
      ebitMargin: p.ebit_margin ?? null,
      capitalDeduction,
      cashFlow,
      capitalDeductionLabel: p.capital_deduction_label ?? "Reinvestment",
      cashFlowLabel: p.free_cash_flow_to_equity != null ? "Free Cash Flow to Equity" : "Unlevered Free Cash Flow",
    }
  })
}

type RowDef = {
  key: keyof ProjectionYear
  label: string
  kind: "money" | "pct" | "outflow"
  accent?: boolean
  hidden?: boolean
}

const scenarios: Scenario[] = ["bear", "base", "bull"]

export function ProjectionTable({
  scenario,
  onScenarioChange,
  dcfData,
}: {
  scenario: Scenario
  onScenarioChange: (s: Scenario) => void
  dcfData?: DCFData
}) {
  const dataList = dynamicScenarioProjection(scenario, dcfData)
  const firstProjection = dataList[0]
  const regulatoryFcfe = isRegulatoryFcfe(dcfData)
  const primaryDriverLabel = regulatoryFcfe ? "Projected Net Income" : "Projected Revenue"
  const growthLabel = regulatoryFcfe ? "Net Income Growth" : "Revenue Growth"
  const capitalDeductionLabel = firstProjection?.capitalDeductionLabel ?? (
    regulatoryFcfe ? "Required Regulatory Capital" : "Reinvestment"
  )
  const cashFlowLabel = firstProjection?.cashFlowLabel ?? (
    regulatoryFcfe ? "Free Cash Flow to Equity" : "Unlevered Free Cash Flow"
  )
  const rowDefs: RowDef[] = [
    { key: "primaryDriver", label: primaryDriverLabel, kind: "money" },
    { key: "growth", label: growthLabel, kind: "pct" },
    { key: "nopat", label: "NOPAT", kind: "money", hidden: regulatoryFcfe },
    { key: "capitalDeduction", label: capitalDeductionLabel, kind: "outflow" },
    { key: "cashFlow", label: cashFlowLabel, kind: "money", accent: true },
  ]
  const rows = rowDefs.filter((row) => !row.hidden)

  return (
    <GlassCard>
      <div className="flex flex-col gap-3 border-b border-emerald-900/20 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-emerald-900/30 bg-emerald-900/10 text-emerald-400">
            <Table className="h-4 w-4" />
          </span>
          <div>
            <h3 className="text-sm font-semibold text-[#E0E6E2]">{dataList.length}-Year Projection Array</h3>
            <p className="text-[11px] text-[#869E8F]">Driver-based {cashFlowLabel} build-up ($B) · inputs to the DCF fair value</p>
          </div>
        </div>

        {/* Scenario segment pill toggle */}
        <div
          role="radiogroup"
          aria-label="Projection scenario"
          className="inline-flex items-center gap-1 rounded-md border border-emerald-900/20 bg-[#090A0B] p-1"
        >
          {scenarios.map((s) => {
            const active = scenario === s
            const meta = scenarioMeta[s]
            return (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => onScenarioChange(s)}
                className={`flex min-h-11 items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-medium ${
                  active
                    ? meta.classes
                    : "border-transparent text-[#869E8F] hover:text-[#E0E6E2]"
                }`}
              >
                {s === "bear" && <TrendingDown className="h-3.5 w-3.5" />}
                {s === "base" && <Minus className="h-3.5 w-3.5" />}
                {s === "bull" && <TrendingUp className="h-3.5 w-3.5" />}
                {meta.label}
              </button>
            )
          })}
        </div>
      </div>
      <p id="projection-scroll-hint" className="px-4 pt-3 text-[11px] text-[#869E8F] sm:hidden">Swipe horizontally to compare projection years.</p>
      <div className="relative">
      <div
        className="max-w-full overflow-x-auto overscroll-x-contain p-2 [scroll-padding-left:9rem] [scroll-snap-type:x_proximity] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#B7FF3C] sm:p-4 sm:[scroll-padding-left:12rem]"
        role="region"
        aria-label="Projection years table"
        aria-describedby="projection-scroll-hint"
        tabIndex={dataList.length > 0 ? 0 : -1}
      >
        {dataList.length > 0 ? (
          <table className="w-full min-w-[1120px] table-fixed border-collapse text-sm">
          <thead>
            <tr className="text-xs text-[#869E8F]">
              <th className="sticky left-0 z-30 w-36 min-w-36 max-w-36 border-r border-[#294231] bg-[#090A0B] px-3 py-1.5 text-left font-medium shadow-[12px_0_18px_-14px_rgba(183,255,60,0.55)] sm:w-48 sm:min-w-48 sm:max-w-48" data-testid="projection-sticky-label">Line Item</th>
              {dataList.map((p) => (
                <th key={p.year} className="w-20 min-w-20 snap-start px-3 py-1.5 text-right font-medium">
                  Year {p.year}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.key}
                className={`border-t border-emerald-900/20 ${
                  row.accent ? "bg-emerald-500/[0.04]" : ""
                }`}
              >
                <td
                  className={`sticky left-0 z-20 w-36 min-w-36 max-w-36 border-r border-[#294231] bg-[#090A0B] px-3 py-2 text-left text-xs shadow-[12px_0_18px_-14px_rgba(183,255,60,0.55)] sm:w-48 sm:min-w-48 sm:max-w-48 ${
                    row.accent ? "font-semibold text-emerald-300" : "text-[#E0E6E2]"
                  }`}
                >
                  {row.label}
                </td>
                {dataList.map((p) => {
                  const val = p[row.key] as number | null
                  const isCost = row.kind === "outflow"
                  return (
                    <td
                      key={p.year}
                      className={`w-20 min-w-20 snap-start px-3 py-2 text-right font-mono tabular-nums ${
                        row.accent
                          ? "font-semibold text-emerald-400"
                          : isCost
                            ? "text-amber-400/90"
                            : "text-[#E0E6E2]"
                      }`}
                    >
                      <span
                        key={`${scenario}-${p.year}`}
                        className="inline-block"
                      >
                        {typeof val === "number" && Number.isFinite(val)
                          ? row.kind === "pct"
                            ? `${(val * 100).toFixed(1)}%`
                            : `${isCost ? "(" : ""}${fmt.money(val / 1e9, 2)}${isCost ? ")" : ""}`
                          : "-"}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        ) : (
          <div className="px-3 py-8 text-sm text-[#869E8F]">
            Projection rows require calculated DCF revenue drivers.
          </div>
        )}
      </div>
      <div className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-[#111613] to-transparent sm:hidden" aria-hidden="true" />
      </div>
    </GlassCard>
  )
}
