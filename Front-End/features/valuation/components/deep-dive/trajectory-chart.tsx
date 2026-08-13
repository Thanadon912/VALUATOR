"use client"

import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { TrendingUp } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt, scenarioMeta, type Scenario } from "@/lib/valuation"
import type { DCFData } from "../DCFCard"
import { dynamicScenarioProjection } from "./projection-table"

type ChartRow = {
  year: string
  primaryDriver: number
  fcfMargin: number
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { payload: ChartRow }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  return (
    <div className="rounded-md border border-emerald-500/20 bg-[#090A0B] px-3.5 py-2.5">
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-[#869E8F]">{label}</p>
      <div className="flex items-center justify-between gap-6">
        <span className="flex items-center gap-1.5 text-xs text-[#869E8F]">
          <span className="h-2 w-2 rounded-sm bg-emerald-500" />
          Driver
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums text-[#E0E6E2]">
          {fmt.bn(row.primaryDriver)}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-6">
        <span className="flex items-center gap-1.5 text-xs text-[#869E8F]">
          <span className="h-2 w-2 rounded-full bg-[#869E8F]" />
          FCF Margin
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums text-[#E0E6E2]">
          {fmt.money(row.fcfMargin)}%
        </span>
      </div>
    </div>
  )
}

export function TrajectoryChart({ scenario, data }: { scenario: Scenario; data?: DCFData }) {
  const rows = dynamicScenarioProjection(scenario, data)
  const chartData: ChartRow[] = rows.map((p) => ({
    year: `Y${p.year}`,
    primaryDriver: p.primaryDriver / 1e9,
    fcfMargin: p.primaryDriver > 0 ? (p.cashFlow / p.primaryDriver) * 100 : 0,
  }))
  const driverLabel = data?.valuation_methodology === "Regulatory FCFE" ? "net income" : "revenue"

  return (
    <GlassCard>
      <CardHeading
        title="Fundamental Trajectory"
        subtitle={`${rows.length}-year ${driverLabel} and cash flow margin - ${scenarioMeta[scenario].label}`}
        icon={<TrendingUp className="h-4 w-4" />}
      />
      <div className="h-80 p-5">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 720, height: 320 }}>
            <ComposedChart data={chartData} margin={{ top: 12, right: 8, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id="trajectoryRevenueBar" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(16 185 129)" stopOpacity={0.8} />
                  <stop offset="100%" stopColor="rgb(16 185 129)" stopOpacity={0.1} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(30 41 59 / 0.6)" vertical={false} />
              <XAxis
                dataKey="year"
                tick={{ fill: "rgb(148 163 184)", fontSize: 11 }}
                axisLine={{ stroke: "rgb(30 41 59)" }}
                tickLine={false}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: "rgb(100 116 139)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `$${Math.round(Number(value))}B`}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                domain={["auto", "auto"]}
                tick={{ fill: "rgb(52 211 153)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `${Number(value).toFixed(0)}%`}
              />
              <Tooltip cursor={{ fill: "rgb(30 41 59 / 0.35)" }} content={<CustomTooltip />} />
              <Bar yAxisId="left" dataKey="primaryDriver" radius={[2, 2, 0, 0]} maxBarSize={46} isAnimationActive={false}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill="url(#trajectoryRevenueBar)" />
                ))}
              </Bar>
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="fcfMargin"
                stroke="rgb(148 163 184)"
                strokeWidth={2}
                dot={{ r: 3, fill: "#090A0B", stroke: "rgb(148 163 184)", strokeWidth: 2 }}
                activeDot={{ r: 5, fill: "rgb(148 163 184)", stroke: "#090A0B", strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center px-3 text-sm text-[#869E8F]">
            Trajectory requires calculated DCF projection drivers.
          </div>
        )}
      </div>
    </GlassCard>
  )
}
