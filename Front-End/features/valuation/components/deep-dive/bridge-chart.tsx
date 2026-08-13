"use client"

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts"
import { GitBranch } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import type { DCFData } from "../DCFCard"

type BridgeStepType = "total" | "minus" | "plus" | "result"
type BridgeBar = {
  name: string
  bar: [number, number]
  type: BridgeStepType
  value: number
  label: string
}

function toFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function formatBridgeValue(valueInBillions: number) {
  const abs = Math.abs(valueInBillions)
  const sign = valueInBillions < 0 ? "-" : ""
  if (abs === 0) return "$0"
  if (abs < 1) return `${sign}$${(abs * 1000).toFixed(0)}M`
  return `${sign}$${abs.toFixed(2)}B`
}

function toBars(steps: { name: string; value: number; type: BridgeStepType }[]): BridgeBar[] {
  let running = 0
  const BASE = 0
  return steps.map((step) => {
    if (step.type === "total" || step.type === "result") {
      running = step.value
      return { name: step.name, bar: [BASE, step.value] as [number, number], type: step.type, value: step.value, label: formatBridgeValue(step.value) }
    }
    const start = running
    running += step.value
    return {
      name: step.name,
      bar: [Math.min(start, running), Math.max(start, running)] as [number, number],
      type: step.type,
      value: step.value,
      label: formatBridgeValue(step.value),
    }
  })
}

// Enterprise-value bridge: only valid for engines that actually discount an
// unlevered cash flow to an enterprise value (Standard/Capitalized R&D/
// Normalized Median DCF). Regulatory FCFE discounts equity cash flow directly
// and never produces an enterprise_value, so this must return null rather
// than let a missing EV render as a fabricated $0 bar.
function buildEnterpriseValueBridge(data: DCFData): BridgeBar[] | null {
  const assumptions = data.underlying_assumptions
  const ev = toFinite(assumptions?.enterprise_value)
  const equity = toFinite(assumptions?.equity_value)
  if (ev === null || equity === null) return null

  let debt = (toFinite(assumptions?.total_debt) ?? toFinite(assumptions?.target_debt) ?? 0) / 1e9
  let cash = (toFinite(assumptions?.cash) ?? toFinite(assumptions?.target_cash) ?? 0) / 1e9
  const evB = ev / 1e9
  const equityB = equity / 1e9

  if (debt === 0 && cash === 0) {
    if (evB > equityB) {
      debt = evB - equityB
      cash = 0
    } else {
      debt = 0
      cash = equityB - evB
    }
  }

  return toBars([
    { name: "Enterprise Value", value: Number(evB.toFixed(2)), type: "total" },
    { name: "Total Debt", value: -Number(debt.toFixed(2)), type: "minus" },
    { name: "Cash & Equiv.", value: Number(cash.toFixed(2)), type: "plus" },
    { name: "Net Equity Value", value: Number(equityB.toFixed(2)), type: "result" },
  ])
}

// Equity-composition bridge for engines (Regulatory FCFE) that discount
// equity cash flow directly at cost of equity rather than routing through an
// enterprise value.
function buildFcfeCompositionBridge(data: DCFData): BridgeBar[] | null {
  const assumptions = data.underlying_assumptions
  const pvFcfe = toFinite(assumptions?.present_value_fcfe)
  const pvTerminal = toFinite(assumptions?.present_value_terminal_value)
  const equity = toFinite(assumptions?.equity_value)
  if (pvFcfe === null || pvTerminal === null || equity === null) return null

  return toBars([
    { name: "PV of Projected FCFE", value: Number((pvFcfe / 1e9).toFixed(2)), type: "plus" },
    { name: "PV of Terminal Value", value: Number((pvTerminal / 1e9).toFixed(2)), type: "plus" },
    { name: "Equity Value", value: Number((equity / 1e9).toFixed(2)), type: "result" },
  ])
}

const colorFor = (type: string) =>
  type === "total"
    ? "rgb(71 85 105)"
    : type === "result"
      ? "rgb(16 185 129)"
      : type === "plus"
        ? "rgb(52 211 153)"
        : "rgb(245 158 11)"

export function BridgeChart({ data: dcfData }: { data?: DCFData }) {
  const evBridge = dcfData ? buildEnterpriseValueBridge(dcfData) : null
  const fcfeBridge = !evBridge && dcfData ? buildFcfeCompositionBridge(dcfData) : null
  const data = evBridge ?? fcfeBridge ?? []
  const subtitle = evBridge
    ? "Enterprise Value → Net Equity Value ($B)"
    : fcfeBridge
      ? "PV of FCFE + Terminal Value → Equity Value ($B)"
      : "Enterprise Value → Net Equity Value ($B)"

  return (
    <GlassCard>
      <CardHeading
        title="Financial Bridge"
        subtitle={subtitle}
        icon={<GitBranch className="h-4 w-4" />}
      />
      <div className="h-72 p-5">
        {data.length > 0 ? (
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 680, height: 288 }}>
          <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
            <XAxis
              dataKey="name"
              tick={{ fill: "rgb(148 163 184)", fontSize: 11 }}
              axisLine={{ stroke: "rgb(30 41 59)" }}
              tickLine={false}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fill: "rgb(100 116 139)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => formatBridgeValue(Number(v))}
            />
            <Tooltip
              cursor={{ fill: "rgba(16, 185, 129, 0.05)" }}
              contentStyle={{
                background: "#090A0B",
                border: "1px solid rgba(16, 185, 129, 0.2)",
                borderRadius: 6,
                fontSize: 12,
              }}
              labelStyle={{ color: "rgb(148 163 184)" }}
              formatter={(_v, _n, item) => [formatBridgeValue(item.payload.value as number), item.payload.name]}
            />
            <Bar dataKey="bar" radius={[4, 4, 4, 4]} isAnimationActive={false}>
              <LabelList
                dataKey="label"
                position="top"
                fill="rgb(203 213 225)"
                fontSize={11}
                fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
              />
              {data.map((d, i) => (
                <Cell key={i} fill={colorFor(d.type)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center px-3 text-sm text-[#869E8F]">
            Financial bridge requires a calculated enterprise value or equity composition.
          </div>
        )}
      </div>
    </GlassCard>
  )
}
