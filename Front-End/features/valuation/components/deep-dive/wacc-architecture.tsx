"use client"

import { Layers, Plus } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"
import type { DCFData } from "../DCFCard"
import { isRegulatoryFcfe } from "../DCFCard"

function percent(value?: number | null, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "N/A"
  return `${(value * 100).toFixed(digits)}%`
}

function Factor({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center rounded-md border border-emerald-900/20 bg-[#090A0B] px-2 py-2.5 sm:px-3">
      <span className="font-mono text-base font-semibold tabular-nums text-[#E0E6E2]">{value}</span>
      <span className="mt-0.5 text-center text-[9px] uppercase leading-4 tracking-wider text-[#869E8F] sm:text-[10px]">{label}</span>
    </div>
  )
}

function ComponentBlock({
  title,
  weight,
  cost,
  tint,
  testId,
  costLabel = "Cost",
}: {
  title: string
  weight: string
  cost: string
  tint: string
  testId: string
  costLabel?: string
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2" data-testid={testId}>
      <span className={`text-[11px] font-medium uppercase tracking-wider ${tint}`}>{title}</span>
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-1">
        <Factor label="Weight" value={weight} />
        <span className="font-mono text-lg text-[#869E8F]">x</span>
        <Factor label={costLabel} value={cost} />
      </div>
    </div>
  )
}

export function WaccArchitecture({ data }: { data?: DCFData }) {
  const components = data?.underlying_assumptions?.wacc_components
  const fallbackWacc = data?.underlying_assumptions?.wacc
  const costOfEquity = data?.underlying_assumptions?.discount_rate ?? data?.underlying_assumptions?.cost_of_equity
  const equityOnly = isRegulatoryFcfe(data)
  const trueWacc = components?.wacc ?? fallbackWacc

  return (
    <GlassCard>
      <CardHeading
        title={equityOnly ? "Discount Rate Architecture" : "WACC Architecture"}
        subtitle={
          equityOnly
            ? "Regulatory FCFE - discounted at Cost of Equity"
            : "Weighted equity and after-tax debt cost build-up"
        }
        icon={<Layers className="h-4 w-4" />}
        tooltipText="Visualizes the Weighted Average Cost of Capital, blending the cost of equity and after-tax cost of debt to determine the discount rate."
        badge={
          equityOnly ? null : (
            <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 font-mono text-xs font-semibold tabular-nums text-emerald-400">
              {percent(components?.effective_tax_rate, 1)} tax
            </span>
          )
        }
      />

      {equityOnly ? (
        <div className="flex flex-col items-center gap-4 p-8 text-center">
          <div className="flex flex-col items-center rounded-md border border-emerald-500/20 bg-emerald-500/10 px-10 py-5">
            <span className="font-mono text-4xl font-bold tabular-nums text-emerald-400">
              {typeof costOfEquity === "number" && Number.isFinite(costOfEquity)
                ? fmt.money(costOfEquity * 100, 2)
                : "N/A"}
              %
            </span>
            <span className="mt-1 text-xs font-medium text-emerald-500/80">
              Cost of Equity (Ke)
            </span>
          </div>
          <p className="max-w-md text-xs leading-relaxed text-[#869E8F]">
            WACC is not used for financial institutions. The regulatory FCFE engine discounts equity cash flow directly at Ke.
          </p>
        </div>
      ) : (
      <div className="grid items-center gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(148px,0.55fr)]" data-testid="wacc-equation">
          <ComponentBlock
            title="Equity"
            weight={percent(components?.weight_equity, 1)}
            cost={percent(components?.cost_of_equity, 1)}
            tint="text-[#E0E6E2]"
            testId="wacc-equity-term"
          />

          <span className="mx-auto flex h-8 w-8 items-center justify-center rounded-full border border-emerald-900/20 bg-[#090A0B] text-[#869E8F]" role="img" aria-label="plus">
            <Plus className="h-4 w-4" />
          </span>

          <ComponentBlock
            title="Debt"
            weight={percent(components?.weight_debt, 1)}
            cost={percent(components?.cost_of_debt_after_tax ?? components?.cost_of_debt, 1)}
            tint="text-amber-400"
            testId="wacc-debt-term"
            costLabel="After-tax cost"
          />

          <span className="mx-auto font-mono text-2xl text-[#869E8F]" role="img" aria-label="equals">=</span>
          <div className="flex min-w-0 flex-col items-center rounded-md border border-emerald-500/20 bg-emerald-500/10 px-4 py-4" data-testid="wacc-result">
            <span className="font-mono text-3xl font-bold tabular-nums text-emerald-400">
              {typeof trueWacc === "number" && Number.isFinite(trueWacc)
                ? fmt.money(trueWacc * 100, 2)
                : "N/A"}
              %
            </span>
            <span className="mt-0.5 text-xs font-medium text-emerald-500/80">
              Model WACC
            </span>
          </div>
      </div>
      )}
    </GlassCard>
  )
}
